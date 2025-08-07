import locale, logging

def get_user_locale():
    """
    Get the user's locale.
    
    Returns:
        str: The locale in the format 'language_country' (e.g., 'en_US').
              Defaults to 'en' if locale cannot be determined.
    """
    user_locale = locale.getdefaultlocale()[0]  # E.g., 'en_US'
    return user_locale if user_locale is not None else 'en'  # Fallback to 'en'

def get_mac_address_from_ip(ip_address):
    """
    Get MAC address for an IP address.
    
    Args:
        ip_address (str): IP address to look up
        
    Returns:
        str or None: MAC address or None if not found
    """
    try:
        from getmac import get_mac_address
        return get_mac_address(ip=ip_address)
    except ImportError:
        logging.debug("getmac library not available - install with: pip install getmac")
        return None
    except Exception as e:
        logging.debug(f"Failed to get MAC for {ip_address}: {e}")
        return None


def get_user_message(message_dict, error_key, user_locale, default_message="Unknown error.", **kwargs):
    """
    Retrieve a localized message from the provided dictionary.

    Parameters:
        message_dict (dict): A dictionary of localized messages.
        error_key (str): The key for the specific message.
        user_locale (str): The user's locale.
        default_message (str): The fallback message if key is not found.
        **kwargs: Additional parameters for message formatting.

    Returns:
        str: The localized message.
    """
    lang = user_locale.split('_')[0]  # Extract language code
    
    # Fallback chain: user_lang -> en -> default_message
    if lang in message_dict and error_key in message_dict[lang]:
        message_template = message_dict[lang][error_key]
    elif "en" in message_dict and error_key in message_dict["en"]:
        message_template = message_dict["en"][error_key]
    else:
        # Log missing translation for debugging
        logging.warning(f"Missing translation for key '{error_key}' in language '{lang}' - using default")
        return default_message
    
    try:
        return message_template.format(**kwargs)
    except KeyError as e:
        logging.warning(f"Missing parameter {e} for message key '{error_key}' - using unformatted message")
        return message_template
    except Exception as e:
        logging.warning(f"Error formatting message '{error_key}': {e} - using default")
        return default_message

def log_message(message_dict, log_key, user_locale, level=logging.INFO, **kwargs):
    """
    Log a localized message with improved error handling.
    
    Parameters:
        message_dict (dict): A dictionary of localized messages.
        log_key (str): The key for the specific log message.
        user_locale (str): The user's locale.
        level (int): Logging level.
        **kwargs: Additional parameters for message formatting.
    """
    lang = user_locale.split('_')[0]  # Extract language code
    
    # Fallback chain: user_lang -> en -> create default message
    if lang in message_dict and log_key in message_dict[lang]:
        message_template = message_dict[lang][log_key]
    elif "en" in message_dict and log_key in message_dict["en"]:
        message_template = message_dict["en"][log_key]
    else:
        # Create a descriptive default message instead of "Unknown log message"
        message_template = f"MaxSmart log [{log_key}] - Missing translation for language '{lang}'"
        if kwargs:
            # Add parameter info if available
            params_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            message_template += f" (params: {params_str})"
        
        logging.log(level, message_template)
        return
    
    try:
        formatted_message = message_template.format(**kwargs)
        logging.log(level, formatted_message)
    except KeyError as e:
        # Missing parameter - log what we can
        missing_param = str(e).strip("'\"")
        fallback_message = f"MaxSmart log [{log_key}] - Missing parameter '{missing_param}' for message formatting"
        if kwargs:
            available_params = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            fallback_message += f" (available: {available_params})"
        logging.log(level, fallback_message)
    except Exception as e:
        # Other formatting errors
        fallback_message = f"MaxSmart log [{log_key}] - Message formatting error: {e}"
        if kwargs:
            params_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            fallback_message += f" (params: {params_str})"
        logging.log(level, fallback_message)