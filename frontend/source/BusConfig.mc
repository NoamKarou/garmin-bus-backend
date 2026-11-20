using Toybox.Application as App;
using Toybox.Lang;

class BusConfig {
    public var backendUrl as Lang.String;
    public var lineNumbers as Lang.String;
    public var stationCode as Lang.String;
    public var refreshSeconds as Lang.Number;

    function initialize() {
        backendUrl = _stringProperty("BackendUrl", "http://127.0.0.1:8000");
        lineNumbers = BusUtil.trim(_stringProperty("LineNumbers", "481"));
        stationCode = BusUtil.trim(_stringProperty("StationCode", "4170"));
        refreshSeconds = _numberProperty("RefreshSeconds", 30);

        if (refreshSeconds < 15) {
            refreshSeconds = 15;
        }
        if (refreshSeconds > 300) {
            refreshSeconds = 300;
        }

        var trimmed = backendUrl;
        while (trimmed.length() > 0) {
            var last = trimmed.substring(trimmed.length() - 1, trimmed.length()) as Lang.String;
            if (!last.equals("/")) {
                break;
            }
            trimmed = trimmed.substring(0, trimmed.length() - 1) as Lang.String;
        }
        backendUrl = trimmed;
    }

    function isConfigured() as Lang.Boolean {
        return lineNumbers.length() > 0 && stationCode.length() > 0;
    }

    private function _stringProperty(key as Lang.String, fallback as Lang.String) as Lang.String {
        var value = App.Properties.getValue(key);
        if (value instanceof Lang.String && (value as Lang.String).length() > 0) {
            return value as Lang.String;
        }
        return fallback;
    }

    private function _numberProperty(key as Lang.String, fallback as Lang.Number) as Lang.Number {
        var value = App.Properties.getValue(key);
        if (value instanceof Lang.Number) {
            return value as Lang.Number;
        }
        return fallback;
    }
}
