import os
from dotenv import load_dotenv


load_dotenv()

def get_env_variable(var_name, default=None):
    """
    Retrieves an environment variable.

    Args:
        var_name (str): The name of the environment variable.
        default: The default value to return if the variable is not found.

    Returns:
        The value of the environment variable or the default value.
    """
    return os.getenv(var_name, default)

def get_local_dir():
    return(os.path.dirname(os.path.realpath(__file__)))

