using Toybox.Application as App;
using Toybox.Lang;
using Toybox.Time;

class BusStore {
    public var arrivals as Lang.Array = [] as Lang.Array;
    public var stationName as Lang.String? = null;
    public var stationCode as Lang.String? = null;
    public var lastUpdatedSec as Lang.Number = 0;
    public var stale as Lang.Boolean = false;
    public var loading as Lang.Boolean = false;
    public var error as Lang.String? = null;

    function initialize() {
    }

    function applyResponse(data as Lang.Dictionary) as Lang.Boolean {
        var arrivalsRaw = data["arrivals"];
        if (!(arrivalsRaw instanceof Lang.Array)) {
            return false;
        }

        var normalized = [] as Lang.Array;
        var array = arrivalsRaw as Lang.Array;
        var nowSec = Time.now().value();

        for (var i = 0; i < array.size(); i++) {
            var item = array[i];
            if (!(item instanceof Lang.Dictionary)) {
                continue;
            }
            var dict = item as Lang.Dictionary;
            var line = dict["line"];
            var epochSec = dict["arrival_epoch_sec"];
            if (!(line instanceof Lang.String) || !(epochSec instanceof Lang.Number)) {
                continue;
            }

            var remainingSec = (epochSec as Lang.Number) - nowSec;
            var minutes = 0;
            if (remainingSec > 0) {
                minutes = (remainingSec + 59) / 60;
            }

            normalized.add({
                "line" => line as Lang.String,
                "minutes" => minutes,
                "live" => dict["live"] == true
            } as Lang.Dictionary);
        }

        arrivals = normalized;

        var stationRaw = data["station"];
        if (stationRaw instanceof Lang.Dictionary) {
            var station = stationRaw as Lang.Dictionary;
            var name = station["name"];
            var code = station["code"];
            stationName = name instanceof Lang.String ? name as Lang.String : null;
            stationCode = code instanceof Lang.String ? code as Lang.String : null;
        }

        lastUpdatedSec = nowSec;
        stale = false;
        loading = false;
        error = null;
        save();
        return true;
    }

    function markError(message as Lang.String, keepData as Lang.Boolean) as Void {
        error = message;
        loading = false;
        if (keepData && arrivals.size() > 0) {
            stale = true;
        } else {
            arrivals = [] as Lang.Array;
            stale = false;
        }
    }

    function save() as Void {
        try {
            var name = stationName == null ? "" : stationName as Lang.String;
            var code = stationCode == null ? "" : stationCode as Lang.String;
            App.Storage.setValue("busLastGood", {
                "arrivals" => arrivals as Lang.Array<App.Storage.ValueType>,
                "stationName" => name,
                "stationCode" => code,
                "savedAt" => lastUpdatedSec
            } as Lang.Dictionary<App.Storage.KeyType, App.Storage.ValueType>);
        } catch (e) {
            // Storage may be full; live data still works without the cache.
        }
    }

    function load() as Lang.Boolean {
        try {
            var saved = App.Storage.getValue("busLastGood");
            if (!(saved instanceof Lang.Dictionary)) {
                return false;
            }
            var dict = saved as Lang.Dictionary;

            var savedAt = dict["savedAt"];
            if (!(savedAt instanceof Lang.Number)) {
                return false;
            }
            if (Time.now().value() - (savedAt as Lang.Number) > 600) {
                return false;
            }

            var savedArrivals = dict["arrivals"];
            if (!(savedArrivals instanceof Lang.Array)) {
                return false;
            }
            arrivals = savedArrivals as Lang.Array;

            var name = dict["stationName"];
            var code = dict["stationCode"];
            stationName = (name instanceof Lang.String && (name as Lang.String).length() > 0)
                    ? name as Lang.String : null;
            stationCode = (code instanceof Lang.String && (code as Lang.String).length() > 0)
                    ? code as Lang.String : null;

            lastUpdatedSec = savedAt as Lang.Number;
            stale = true;
            return true;
        } catch (e) {
            return false;
        }
    }
}
