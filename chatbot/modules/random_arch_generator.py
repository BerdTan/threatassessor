"""
Random Architecture Generator

Generates random but realistic architecture diagrams for testing threat assessment tools.
Useful for validation, benchmarking, and stress testing the parser.

Usage:
    python3 -m chatbot.main --gen-random-arch [--orientation TB|LR] [--complexity low|medium|high]
"""

import random
from typing import List, Tuple, Dict
from pathlib import Path


# Component pools for realistic architectures
ENTRY_POINTS = [
    "Internet", "Public Network", "External Users", "Mobile Clients",
    "Third-Party Services", "Partner API", "Cloud Provider"
]

PERIMETER_DEFENSES = [
    "WAF", "Firewall", "API Gateway", "DDoS Protection",
    "VPN Gateway", "Reverse Proxy", "CDN"
]

LOAD_BALANCERS = [
    "Load Balancer", "Application Load Balancer", "Network Load Balancer",
    "Traffic Manager", "API Gateway"
]

AUTH_COMPONENTS = [
    "Authentication Service", "OAuth Server", "Identity Provider",
    "SSO Gateway", "MFA Service", "LDAP Server"
]

APPLICATION_SERVICES = [
    "Web Server", "API Server", "Application Server",
    "Microservice", "Function App", "Container Service",
    "Message Queue", "Cache Server", "Session Store"
]

DATA_STORES = [
    "Database", "SQL Database", "NoSQL Database",
    "Data Warehouse", "Object Storage", "File Server",
    "Backup Storage", "Archive"
]

MONITORING_LOGGING = [
    "SIEM", "Log Aggregator", "Monitoring System",
    "Alert Service", "Audit Log", "Metrics Collector"
]

SECURITY_CONTROLS = [
    "EDR", "IDS/IPS", "Encryption Service",
    "Key Management", "Secret Vault", "Security Scanner"
]


def generate_component_name(pool: List[str], used_names: set) -> str:
    """Generate a unique component name from a pool."""
    for _ in range(100):  # Avoid infinite loop
        name = random.choice(pool)
        if name not in used_names:
            used_names.add(name)
            return name
    # Fallback: add suffix
    base = random.choice(pool)
    i = 1
    while f"{base} {i}" in used_names:
        i += 1
    name = f"{base} {i}"
    used_names.add(name)
    return name


def get_mermaid_shape(component_type: str, name: str) -> str:
    """Get appropriate Mermaid shape syntax for component type."""
    node_id = name.replace(" ", "").replace("/", "").replace("-", "")

    if component_type == "entry":
        return f'{node_id}(("{name}"))'  # Circle
    elif component_type == "database":
        return f'{node_id}[("{name}")]'  # Cylinder
    elif component_type == "defense":
        return f'{node_id}["{name}"]'     # Rectangle (could be hexagon)
    else:
        return f'{node_id}["{name}"]'     # Rectangle


def generate_random_architecture(
    orientation: str = "TB",
    complexity: str = "medium",
    seed: int = None
) -> Tuple[str, Dict]:
    """
    Generate a random architecture diagram.

    Args:
        orientation: "TB" (top-bottom) or "LR" (left-right)
        complexity: "low" (5-8 nodes), "medium" (10-15 nodes), "high" (20-30 nodes)
        seed: Random seed for reproducibility

    Returns:
        (mermaid_content, metadata)
    """
    if seed is not None:
        random.seed(seed)

    # Determine node count
    if complexity == "low":
        num_nodes = random.randint(5, 8)
    elif complexity == "high":
        num_nodes = random.randint(20, 30)
    else:  # medium
        num_nodes = random.randint(10, 15)

    used_names = set()
    components = []
    edges = []

    # 1. Entry point (always 1)
    entry = generate_component_name(ENTRY_POINTS, used_names)
    components.append(("entry", entry))

    # 2. Perimeter defense (50% chance if complexity > low)
    prev_layer = [entry]
    current_layer = []

    if complexity != "low" and random.random() > 0.5:
        defense = generate_component_name(PERIMETER_DEFENSES, used_names)
        components.append(("defense", defense))
        current_layer.append(defense)
        for prev in prev_layer:
            edges.append((prev, defense))
        prev_layer = current_layer
        current_layer = []

    # 3. Load balancer (optional)
    if num_nodes > 6 and random.random() > 0.4:
        lb = generate_component_name(LOAD_BALANCERS, used_names)
        components.append(("service", lb))
        current_layer.append(lb)
        for prev in prev_layer:
            edges.append((prev, lb))
        prev_layer = current_layer
        current_layer = []

    # 4. Authentication layer (optional)
    if num_nodes > 8 and random.random() > 0.5:
        auth = generate_component_name(AUTH_COMPONENTS, used_names)
        components.append(("service", auth))
        current_layer.append(auth)
        for prev in prev_layer:
            edges.append((prev, auth))
        prev_layer = current_layer
        current_layer = []

    # 5. Application services (main layer)
    app_count = max(1, min(5, num_nodes - len(components) - 2))
    for _ in range(app_count):
        app = generate_component_name(APPLICATION_SERVICES, used_names)
        components.append(("service", app))
        current_layer.append(app)
        # Connect from previous layer
        for prev in prev_layer:
            edges.append((prev, app))

    prev_layer = current_layer
    current_layer = []

    # 6. Data layer
    db_count = max(1, min(3, num_nodes - len(components) - 1))
    for _ in range(db_count):
        db = generate_component_name(DATA_STORES, used_names)
        components.append(("database", db))
        current_layer.append(db)
        # Connect from some app services
        connectable = prev_layer if prev_layer else [components[-2][1]]
        for app in random.sample(connectable, min(len(connectable), random.randint(1, 2))):
            edges.append((app, db))

    # 7. Optional monitoring/logging (if space remains)
    if len(components) < num_nodes and complexity != "low":
        remaining = num_nodes - len(components)
        monitor_count = min(2, remaining)
        for _ in range(monitor_count):
            monitor = generate_component_name(MONITORING_LOGGING, used_names)
            components.append(("service", monitor))
            # Connect from random services
            connectable = [c[1] for c in components if c[0] in ["service", "database"]]
            if connectable:
                source = random.choice(connectable)
                edges.append((source, monitor))

    # 8. Optional security controls (if space remains)
    if len(components) < num_nodes and complexity == "high":
        remaining = num_nodes - len(components)
        security_count = min(2, remaining)
        for _ in range(security_count):
            sec = generate_component_name(SECURITY_CONTROLS, used_names)
            components.append(("defense", sec))
            # Connect to random components
            connectable = [c[1] for c in components[:-1] if c[0] == "service"]
            if connectable:
                target = random.choice(connectable)
                edges.append((sec, target))

    # Build Mermaid diagram
    lines = [f"flowchart {orientation}"]
    lines.append("")

    # Add nodes
    for comp_type, name in components:
        lines.append(f"    {get_mermaid_shape(comp_type, name)}")

    lines.append("")

    # Add edges
    for src, dst in edges:
        src_id = src.replace(" ", "").replace("/", "").replace("-", "")
        dst_id = dst.replace(" ", "").replace("/", "").replace("-", "")
        lines.append(f"    {src_id} --> {dst_id}")

    mermaid_content = "\n".join(lines)

    # Metadata
    metadata = {
        "orientation": orientation,
        "complexity": complexity,
        "node_count": len(components),
        "edge_count": len(edges),
        "seed": seed,
        "entry_points": [c[1] for c in components if c[0] == "entry"],
        "databases": [c[1] for c in components if c[0] == "database"],
    }

    return mermaid_content, metadata


def save_random_architecture(
    output_path: str,
    orientation: str = "TB",
    complexity: str = "medium",
    seed: int = None
) -> Path:
    """
    Generate and save a random architecture to file.

    Returns:
        Path to saved file
    """
    mermaid_content, metadata = generate_random_architecture(orientation, complexity, seed)

    # Determine filename
    if output_path:
        file_path = Path(output_path)
    else:
        # Auto-generate name
        seed_str = f"_seed{seed}" if seed else ""
        filename = f"random_{complexity}_{orientation}{seed_str}.mmd"
        file_path = Path("tests/data/architectures") / filename

    # Ensure directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Add metadata comment
    header = f"%%  Random Architecture - {complexity.capitalize()} Complexity\n"
    header += f"%%  Orientation: {orientation}, Nodes: {metadata['node_count']}, Edges: {metadata['edge_count']}\n"
    if seed is not None:
        header += f"%%  Seed: {seed} (use same seed for reproducibility)\n"
    header += "\n"

    with open(file_path, 'w') as f:
        f.write(header)
        f.write(mermaid_content)

    return file_path


if __name__ == "__main__":
    # Test generation
    import sys

    orientation = sys.argv[1] if len(sys.argv) > 1 else "TB"
    complexity = sys.argv[2] if len(sys.argv) > 2 else "medium"
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else random.randint(1000, 9999)

    file_path = save_random_architecture(None, orientation, complexity, seed)
    print(f"Generated: {file_path}")
    print(f"Seed: {seed} (use this seed to regenerate the same architecture)")
