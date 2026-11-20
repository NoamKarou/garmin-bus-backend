using Toybox.Graphics as Gfx;
using Toybox.Lang;
using Toybox.Time;
using Toybox.Timer;
using Toybox.WatchUi as Ui;

class BusView extends Ui.View {
    private var _config as BusConfig;
    private var _store as BusStore;
    private var _service as BusService;
    private var _timer as Timer.Timer?;
    private var _watchdog as Timer.Timer?;
    // Bundle fonts with Hebrew glyphs: the built-in FONT_* bitmaps have none.
    private var _stationFont as Ui.FontResource;
    private var _stationTinyFont as Ui.FontResource;
    // Marquee state for station names that are wider than the screen chord.
    private var _scrollTimer as Timer.Timer?;
    private var _scrollPos as Lang.Number;
    private var _scrollName as Lang.String?;

    function initialize() {
        Ui.View.initialize();
        _config = new BusConfig();
        _store = new BusStore();
        _store.load();
        _service = new BusService(_config, method(:onServiceResult));
        _stationFont = Ui.loadResource(Rez.Fonts.HebrewSmall) as Ui.FontResource;
        _stationTinyFont = Ui.loadResource(Rez.Fonts.HebrewTiny) as Ui.FontResource;
        _scrollPos = 0;
        _scrollName = null;
    }

    function onShow() as Void {
        if (_timer == null) {
            _timer = new Timer.Timer();
            _timer.start(method(:onTick), _config.refreshSeconds * 1000, true);
        }
        refresh();
    }

    function onHide() as Void {
        if (_timer != null) {
            _timer.stop();
            _timer = null;
        }
        stopWatchdog();
        stopScrolling();
    }

    function onTick() as Void {
        refresh();
    }

    function refresh() as Void {
        _store.loading = true;
        _store.error = null;
        Ui.requestUpdate();
        if (_service.refresh()) {
            stopWatchdog();
            _watchdog = new Timer.Timer();
            _watchdog.start(method(:onWatchdog), 15000, false);
        }
    }

    function onWatchdog() as Void {
        _watchdog = null;
        if (_store.loading) {
            _store.loading = false;
            _store.error = "No response";
            Ui.requestUpdate();
        }
    }

    function stopWatchdog() as Void {
        if (_watchdog != null) {
            _watchdog.stop();
            _watchdog = null;
        }
    }

    function onServiceResult(data as Lang.Dictionary or Null, code as Lang.Number) as Void {
        stopWatchdog();
        if (data != null) {
            _store.applyResponse(data as Lang.Dictionary);
        } else {
            var keep = _store.arrivals.size() > 0
                    && (Time.now().value() - _store.lastUpdatedSec) <= 600;
            _store.markError(BusService.errorMessage(code), keep);
        }
        Ui.requestUpdate();
    }

    function onUpdate(dc as Gfx.Dc) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();

        dc.setColor(Gfx.COLOR_BLACK, Gfx.COLOR_LT_GRAY);
        dc.clear();

        var station = _config.stationCode;
        if (_store.stationName != null) {
            station = _store.stationName as Lang.String;
        }

        dc.setColor(Gfx.COLOR_BLACK, Gfx.COLOR_TRANSPARENT);
        dc.drawText(
            w / 2, h * 5 / 100, Gfx.FONT_SMALL,
            "Line " + _config.lineNumbers,
            Gfx.TEXT_JUSTIFY_CENTER
        );

        drawStationName(dc, w, h, station);

        if (_store.arrivals.size() == 0) {
            drawEmptyState(dc, w, h);
            drawFooter(dc, w, h);
            return;
        }

        var first = _store.arrivals[0] as Lang.Dictionary;
        var firstLive = first["live"] == true;
        var color = firstLive ? Gfx.COLOR_GREEN : Gfx.COLOR_BLACK;

        dc.setColor(color, Gfx.COLOR_BLUE);
        dc.drawText(
            w / 2, h * 26 / 100, Gfx.FONT_NUMBER_MEDIUM,
            "hello",
            Gfx.TEXT_JUSTIFY_CENTER
        );
        dc.drawText(
            w / 2, h * 26 / 100, Gfx.FONT_NUMBER_MEDIUM,
            (first["minutes"] as Lang.Number).toString(),
            Gfx.TEXT_JUSTIFY_CENTER
        );
        dc.drawText(
            w / 2, h * 46 / 100, Gfx.FONT_SMALL,
            "min",
            Gfx.TEXT_JUSTIFY_CENTER
        );

        var y = h * 58 / 100;
        var shown = 0;
        for (var i = 1; i < _store.arrivals.size() && shown < 2; i++) {
            var item = _store.arrivals[i] as Lang.Dictionary;
            var live = item["live"] == true;
            dc.setColor(
                live ? Gfx.COLOR_GREEN : Gfx.COLOR_LT_GRAY,
                Gfx.COLOR_TRANSPARENT
            );
            dc.drawText(
                w / 2, y, Gfx.FONT_SMALL,
                (item["minutes"] as Lang.Number).toString() + " min",
                Gfx.TEXT_JUSTIFY_CENTER
            );
            y += h * 8 / 100;
            shown++;
        }

        drawFooter(dc, w, h);
    }

    // Station names come from the backend and are usually Hebrew; the runtime
    // lays RTL text out itself, so the logical string is drawn as is. Near the
    // top of a round screen there is less room than the full width, so fit the
    // name to the chord at this height. Short names stay centered; longer ones
    // scroll as a marquee so the whole name can still be read.
    private function drawStationName(
        dc as Gfx.Dc,
        w as Lang.Number,
        h as Lang.Number,
        station as Lang.String
    ) as Void {
        var y = h * 15 / 100;
        var maxWidth = w * 78 / 100;
        var textWidth = dc.getTextWidthInPixels(station, _stationFont);

        dc.setColor(Gfx.COLOR_BLACK, Gfx.COLOR_TRANSPARENT);

        if (textWidth <= maxWidth) {
            stopScrolling();
            _scrollName = null;
            dc.drawText(w / 2, y, _stationFont, station, Gfx.TEXT_JUSTIFY_CENTER);
            return;
        }

        if (_scrollName == null || !(_scrollName as Lang.String).equals(station)) {
            _scrollName = station;
            _scrollPos = 0;
        }
        startScrolling();

        var gap = 60;
        var period = textWidth + gap;
        var offset = _scrollPos % period;
        var left = (w - maxWidth) / 2;
        var fontHeight = dc.getFontHeight(_stationFont);
        var x = 0;

        dc.setClip(left, y, maxWidth, fontHeight);
        if (isRtl(station)) {
            // An RTL name starts at its right edge. Anchor that edge at the
            // right of the window and let the text travel rightwards; the
            // characters that come into view on the left are the ones read
            // next. The second copy keeps the loop seamless.
            x = left + maxWidth - textWidth + offset;
            dc.drawText(x, y, _stationFont, station, Gfx.TEXT_JUSTIFY_LEFT);
            dc.drawText(x - period, y, _stationFont, station, Gfx.TEXT_JUSTIFY_LEFT);
        } else {
            x = left - offset;
            dc.drawText(x, y, _stationFont, station, Gfx.TEXT_JUSTIFY_LEFT);
            dc.drawText(x + period, y, _stationFont, station, Gfx.TEXT_JUSTIFY_LEFT);
        }
        dc.clearClip();
    }

    // True when the text contains right-to-left characters (Hebrew, Arabic,
    // ...), so the marquee can reveal it in reading order.
    private function isRtl(text as Lang.String) as Lang.Boolean {
        var chars = text.toCharArray();
        for (var i = 0; i < chars.size(); i++) {
            var code = (chars[i] as Lang.Char).toNumber();
            if ((code >= 0x0590 && code <= 0x08FF)
                    || (code >= 0xFB1D && code <= 0xFDFF)
                    || (code >= 0xFE70 && code <= 0xFEFF)) {
                return true;
            }
        }
        return false;
    }

    function onScrollTick() as Void {
        _scrollPos += 15;
        Ui.requestUpdate();
    }

    private function startScrolling() as Void {
        if (_scrollTimer == null) {
            _scrollTimer = new Timer.Timer();
            _scrollTimer.start(method(:onScrollTick), 200, true);
        }
    }

    private function stopScrolling() as Void {
        if (_scrollTimer != null) {
            _scrollTimer.stop();
            _scrollTimer = null;
        }
    }

    private function drawEmptyState(dc as Gfx.Dc, w as Lang.Number, h as Lang.Number) as Void {
        var message = "No buses soon :(";
        var color = Gfx.COLOR_BLACK;

        if (_store.loading) {
            message = "Checking...";
        } else if (_store.error != null) {
            message = BusUtil.safeString(_store.error);
            color = Gfx.COLOR_ORANGE;
        }

        dc.setColor(color, Gfx.COLOR_TRANSPARENT);
        dc.drawText(w / 2, h * 42 / 100, Gfx.FONT_MEDIUM, message, Gfx.TEXT_JUSTIFY_CENTER);
    }

    private function drawFooter(dc as Gfx.Dc, w as Lang.Number, h as Lang.Number) as Void {
        var status = "SCHEDULE";
        var color = Gfx.COLOR_LT_GRAY;

        if (_store.arrivals.size() > 0) {
            var first = _store.arrivals[0] as Lang.Dictionary;
            var live = first["live"] == true;
            status = live ? "LIVE" : "SCHEDULE";
            color = live ? Gfx.COLOR_GREEN : Gfx.COLOR_LT_GRAY;
        }
        if (_store.stale) {
            status = "STALE";
            color = Gfx.COLOR_ORANGE;
        }

        dc.setColor(color, Gfx.COLOR_TRANSPARENT);
        dc.drawText(w / 2, h * 84 / 100, Gfx.FONT_TINY, status, Gfx.TEXT_JUSTIFY_CENTER);

        if (_store.lastUpdatedSec > 0) {
            var age = Time.now().value() - _store.lastUpdatedSec;
            if (age < 0) {
                age = 0;
            }
            dc.setColor(Gfx.COLOR_DK_GRAY, Gfx.COLOR_TRANSPARENT);
            dc.drawText(
                w / 2, h * 85 / 100, Gfx.FONT_XTINY,
                "Updated " + BusUtil.formatAge(age),
                Gfx.TEXT_JUSTIFY_CENTER
            );
        }
    }
}
