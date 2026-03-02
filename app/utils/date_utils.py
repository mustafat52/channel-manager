from dateutil import parser


def parse(date_str: str, fuzzy: bool = True):
    """
    Wrapper around dateutil.parser.parse
    """
    return parser.parse(date_str, fuzzy=fuzzy)