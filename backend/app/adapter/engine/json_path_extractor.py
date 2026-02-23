from jsonpath_ng import parse
from typing import Any, List

class JsonPathExtractor:
    """
    Utility to extract data from a raw JSON payload using JsonPath syntax.
    Falls back gracefully if the path evaluates to nothing.
    """
    
    @staticmethod
    def extract_single(payload: dict, path: str) -> Any:
        """
        Extracts a single value. If multiple are found, returns the first one.
        Returns None if not found.
        """
        jsonpath_expr = parse(path)
        matches = [match.value for match in jsonpath_expr.find(payload)]
        
        if not matches:
            return None
        return matches[0]

    @staticmethod
    def extract_list(payload: dict, path: str) -> List[Any]:
        """
        Extracts a list of values (e.g., an array of invoiceDetails).
        Returns an empty list if not found.
        """
        jsonpath_expr = parse(path)
        matches = [match.value for match in jsonpath_expr.find(payload)]
        return matches
