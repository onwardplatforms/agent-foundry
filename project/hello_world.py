import random


def generate_cat_fun():
    """
    Generates a random cat description.

    Returns:
        str: A description of a cat with a type, name, and favorite toy.
    """
    cat_types = ["Persian", "Siamese", "Maine Coon", "Bengal", "Sphynx"]
    cat_names = ["Whiskers", "Luna", "Simba", "Chloe", "Charlie"]
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


def generate_cat_fun():
    """
    Generates a random cat description.

    Returns:
        str: A description of a cat with a type, name, and favorite toy.
    """
    cat_types = ["Persian", "Siamese", "Maine Coon", "Bengal", "Sphynx"]
    cat_names = ["Whiskers", "Luna", "Simba", "Chloe", "Charlie"]
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


def greet(name=None):
    """
    Prints a greeting message.

    This function prints "Hello, World!" to the console.
    """
    if name:
        print(f"Hello, {name}!")
    else:
        print("Hello, World!")


# Call the greet function
import sys

# Call the greet function with command-line argument
if len(sys.argv) > 1:
    greet(sys.argv[1])
else:
    greet()
