using Toybox.Application as App;
using Toybox.WatchUi as Ui;

class BusApp extends App.AppBase {
    function initialize() {
        App.AppBase.initialize();
    }

    function getInitialView() {
        var view = new BusView();
        var delegate = new BusDelegate(view);
        return [view, delegate];
    }
}
