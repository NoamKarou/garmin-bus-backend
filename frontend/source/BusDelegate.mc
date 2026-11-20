using Toybox.Lang;
using Toybox.WatchUi as Ui;

class BusDelegate extends Ui.BehaviorDelegate {
    private var _view as BusView;

    function initialize(view as BusView) {
        Ui.BehaviorDelegate.initialize();
        _view = view;
    }

    function onSelect() as Lang.Boolean {
        _view.refresh();
        return true;
    }

    function onBack() as Lang.Boolean {
        return false;
    }
}
