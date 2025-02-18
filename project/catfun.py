import random


def generate_cat_fun():
    """
    Generates a random cat description.

    Returns:
        str: A description of a cat with a type, name, and favorite toy.
    """
    cat_types = ["Persian", "Ragdoll", "Maine Coon", "Bengal", "British Shorthair"]
    cat_names = ["Whiskers", "Luna", "Max", "Chloe", "Charlie"]
    cat_toys = [
        "feather wand",
        "laser pointer",
        "ball of yarn",
        "catnip mouse",
        "scratching post",
    ]

    cat_type = random.choice(cat_types)
    cat_name = random.choice(cat_names)
    cat_toy = random.choice(cat_toys)

    return f"The {cat_type} cat named {cat_name} loves to play with a {cat_toy}."


if __name__ == "__main__":
    print(generate_cat_fun())
