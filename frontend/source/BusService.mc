using Toybox.Communications as Comm;
using Toybox.Lang;

class BusService {
    private var _config as BusConfig;
    private var _callback as Lang.Method;
    private var _inFlight as Lang.Boolean = false;

    function initialize(config as BusConfig, callback as Lang.Method) {
        _config = config;
        _callback = callback;
    }

    function isBusy() as Lang.Boolean {
        return _inFlight;
    }

    function refresh() as Lang.Boolean {
        if (_inFlight) {
            return false;
        }
        if (!_config.isConfigured()) {
            _callback.invoke(null, -1);
            return false;
        }

        _inFlight = true;
        var url = _config.backendUrl + "/arrivals?lines=" + _config.lineNumbers
                + "&station=" + _config.stationCode + "&limit=3";

        Comm.makeWebRequest(url, {}, {
            :responseType => Comm.HTTP_RESPONSE_CONTENT_TYPE_JSON
        }, method(:onResponse));
        return true;
    }

    function onResponse(
        code as Lang.Number,
        data as Lang.Dictionary or Lang.String or Null
    ) as Void {
        _inFlight = false;
        if (code == 200 && data instanceof Lang.Dictionary) {
            _callback.invoke(data as Lang.Dictionary, 0);
        } else {
            _callback.invoke(null, code);
        }
    }

    static function errorMessage(code as Lang.Number) as Lang.String {
        if (code == -1) {
            return "Set line and station";
        }
        if (code == 404) {
            return "Station not found";
        }
        if (code == 502 || code == 503 || code == 504) {
            return "Service unavailable";
        }
        if (code == -1001) {
            return "HTTPS required";
        }
        return "No connection";
    }
}
