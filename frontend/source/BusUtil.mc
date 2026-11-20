using Toybox.Lang;

module BusUtil {
    function trim(value as Lang.String) as Lang.String {
        var start = 0;
        var end = value.length();
        while (start < end) {
            var first = value.substring(start, start + 1) as Lang.String;
            if (!first.equals(" ")) {
                break;
            }
            start++;
        }
        while (end > start) {
            var last = value.substring(end - 1, end) as Lang.String;
            if (!last.equals(" ")) {
                break;
            }
            end--;
        }
        return value.substring(start, end) as Lang.String;
    }

    function truncate(value as Lang.String, maxChars as Lang.Number) as Lang.String {
        if (value.length() <= maxChars) {
            return value;
        }
        if (maxChars <= 3) {
            return value.substring(0, maxChars) as Lang.String;
        }
        return (value.substring(0, maxChars - 3) as Lang.String) + "...";
    }

    function safeString(value as Lang.String or Null) as Lang.String {
        if (value == null) {
            return "";
        }
        return value as Lang.String;
    }

    function formatAge(seconds as Lang.Number) as Lang.String {
        if (seconds < 0) {
            seconds = 0;
        }
        if (seconds < 60) {
            return seconds.toString() + "s ago";
        }
        if (seconds < 3600) {
            return (seconds / 60).toString() + "m ago";
        }
        return (seconds / 3600).toString() + "h ago";
    }
}
