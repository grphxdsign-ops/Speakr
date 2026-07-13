from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtWidgets import QApplication


def drain_deferred_deletes(app: QApplication, *, cycles: int = 4) -> None:
    """Run queued QML work and deliver DeferredDelete events synchronously."""

    for _ in range(cycles):
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def dispose_qml_fixture(
    app: QApplication,
    engine: QQmlApplicationEngine,
    *,
    roots: Iterable[QObject] = (),
    windows: Iterable[QQuickWindow] = (),
    components: Iterable[QObject] = (),
    context_objects: Iterable[QObject] = (),
) -> None:
    """Destroy QML before the Python objects exported into its context.

    QML bindings can be evaluated while deferred deletion and scene-graph work
    drains.  Keeping context objects alive until every root and the engine are
    gone prevents teardown-only ``null`` binding failures from escaping a test.
    """

    engine_roots = list(engine.rootObjects())
    qml_roots = list(engine_roots)
    for root in roots:
        if root not in qml_roots:
            qml_roots.append(root)

    fixture_windows = list(windows)
    for root in qml_roots:
        if isinstance(root, QQuickWindow) and root not in fixture_windows:
            fixture_windows.append(root)

    for window in fixture_windows:
        window.hide()

    for root in qml_roots:
        if root in engine_roots:
            continue
        if isinstance(root, QQuickItem):
            root.setParentItem(None)
            root.setParent(None)
        root.deleteLater()

    for component in components:
        component.deleteLater()

    for window in fixture_windows:
        if window not in qml_roots:
            window.close()
            window.deleteLater()

    # Roots loaded through QQmlApplicationEngine are owned by the engine.  Let
    # its destructor dismantle those object trees as a unit; deleting a root
    # first can run delayed bindings after their QML ids have gone null.
    drain_deferred_deletes(app)
    engine.collectGarbage()
    engine.deleteLater()
    drain_deferred_deletes(app)

    for context_object in context_objects:
        close = getattr(context_object, "close", None)
        if callable(close):
            close()
        context_object.deleteLater()
    drain_deferred_deletes(app)
