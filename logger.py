import logging, sys

def setup_logging(log_file, level=logging.INFO):
    """
    Sets up logging configuration.

    Args:
        log_file (str): Path to the log file.
        level: Logging level. Default is logging.INFO.
    """
    logging.basicConfig(level=level,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.FileHandler(log_file, mode="w"), logging.StreamHandler(sys.stdout)])
    
