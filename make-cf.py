import os
import subprocess
import json
import locale

# Try setting a locale that supports currency formatting.
# This tries to set to a default locale that supports currency. If it fails, it falls back to 'en_US.UTF-8'.
try:
    locale.setlocale(locale.LC_ALL, '')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except locale.Error:
        pass  # Fallback to manual formatting if both attempts fail.

def generate_auth_token():
    cmd = 'openssl rand -hex 19 | fold -w1 | awk \'BEGIN{srand()}{a[NR]=$0}END{a[int(1+rand()*19)]=toupper(a[int(1+rand()*16)]); for(i=1;i<=19;i++) printf "%s",a[i]; printf "\\n"}\''
    return subprocess.check_output(cmd, shell=True).decode('utf-8').strip()

def parse_size(size_str):
    """Parse size string like '26.32 GiB' to float value in GiB, then convert to GB."""
    if size_str:
        size_gb = float(size_str.split()[0]) * 1.073741824  # Convert GiB to GB
        return round(size_gb, 2)  # Round to two decimal places
    return 0

def format_storage(memory, ssd):
    """Format storage details for display."""
    memory_gb = parse_size(memory)
    ssd_gb = parse_size(ssd)
    storage_str = f"{memory_gb} GB RAM"
    if ssd_gb > 0:
        storage_str += f", {ssd_gb} GB SSD"
    return storage_str

def format_currency(amount):
    """Format currency with commas for readability."""
    try:
        # Attempt to format currency using the locale module.
        return locale.currency(amount, grouping=True)
    except ValueError:
        # Fallback to manual formatting if locale.currency is not available.
        return f"${amount:,.2f}"

def calculate_monthly_cost(hourly_price, num_instances):
    """Calculate monthly cost based on 24 hours a day for 30 days."""
    return round(24 * 30 * hourly_price * num_instances, 2)

def select_cache_node_type(instances, num_replicas):
    while True:
        sorted_instances = sorted(instances.items(), key=lambda x: max(parse_size(x[1].get("Memory", "0 GiB")), parse_size(x[1].get("SSD", "0 GiB"))))

        for index, (cache_type, attrs) in enumerate(sorted_instances, start=1):
            storage = format_storage(attrs.get("Memory", "0 GiB"), attrs.get("SSD", "0 GiB"))
            price = attrs.get("Price", "N/A")
            print(f"{index}. {cache_type} ({storage}) - {price}")

        choice = int(input("Enter choice number: "))
        selected_instance = sorted_instances[choice - 1]
        cache_type, attrs = selected_instance

        # Calculate and display cost information
        hourly_price_per_instance = float(attrs['Price'].strip('$ hourly'))
        monthly_cost_per_instance = calculate_monthly_cost(hourly_price_per_instance, 1)
        total_monthly_cost = calculate_monthly_cost(hourly_price_per_instance, num_replicas + 1)
        storage = format_storage(attrs.get("Memory", "0 GiB"), attrs.get("SSD", "0 GiB"))
        hourly_price_formatted = format_currency(hourly_price_per_instance)
        total_monthly_cost_formatted = format_currency(total_monthly_cost)
        print(f"You selected {cache_type} with {storage}. This will cost {hourly_price_formatted} hourly and approximately {total_monthly_cost_formatted} per month.")
        
        confirm = input("Confirm this selection? (y/n): ")
        if confirm.lower() == 'y':
            return cache_type
        elif confirm.lower() == 'n':
            try:
                num_replicas = int(input("Enter the number of replicas (0-5, default 1): ") or 1)
                if not 0 <= num_replicas <= 5:
                    raise ValueError("Number of replicas must be between 0 and 5.")
            except ValueError as e:
                print(f"Invalid input: {e}")
                return

def get_instance_details():
    with open('instances.json', 'r') as file:
        return json.load(file)

def update_defaults(content, selected_cache_node_type, auth_token, num_replicas, instances):
    # Adjusting YAML indentation in the description
    description_indent = "  "
    option_indent = "        "

    # Replace placeholders in content
    content = content.replace("$DefaultAuthenticationToken", auth_token)
    content = content.replace("$DefaultCacheNodeType", selected_cache_node_type)
    content = content.replace("$NumberOfReplicas", str(num_replicas))

    # Construct the description and allowed values
    description = f"{description_indent}- The compute and memory capacity of the nodes in the node group. Available options:\n"
    allowed_values = []

    for cache_type, attrs in instances.items():
        storage = format_storage(attrs.get("Memory", "0 GiB"), attrs.get("SSD", "0 GiB"))
        price = attrs.get("Price", "N/A")
        description += f"{option_indent}- {cache_type}: {storage} - {price}\n"
        allowed_values.append(cache_type)

    # Replace in template
    content = content.replace("$CacheNodeTypeDescription", description)
    content = content.replace("$AllowedCacheNodeTypes", str(allowed_values))

    return content

def main():
    instances = get_instance_details()

    with open('banner.txt', 'r') as banner_file:
        banner_contents = banner_file.read()
        print(banner_contents)

    project_name = input("Enter the project name: ")

    with open('elasticache.cf', 'r') as template:
        template_content = template.read()

    auth_token = input(f"Enter an Authentication Token (or press Enter to generate one: {generate_auth_token()}): ").strip()
    if not auth_token:
        auth_token = generate_auth_token()

    try:
        num_replicas = int(input("Enter the number of replicas (0-5, default 1): ") or 1)
        if not 0 <= num_replicas <= 5:
            raise ValueError("Number of replicas must be between 0 and 5.")
    except ValueError as e:
        print(f"Invalid input: {e}")
        return

    selected_cache_node_type = select_cache_node_type(instances, num_replicas)

    updated_template = update_defaults(template_content, selected_cache_node_type, auth_token, num_replicas, instances)

    with open(f"{project_name}.cf.yaml", 'w') as output_file:
        output_file.write(updated_template)

    print(f"CloudFormation template '{project_name}.cf.yaml' has been generated.")

if __name__ == '__main__':
    main()

