from flask import g, jsonify, request


def protect_database_requests(app, lock, get_startup_error):
    """Drain active database requests before restore; exclude static/lookup I/O.

    The production server has one worker and four threads. The shared RLock
    also allows backup routes to acquire it inside the request guard.
    """
    blueprints = {"inventory", "items", "types", "locations", "media", "backups"}

    @app.before_request
    def acquire_database_lock():
        if request.blueprint not in blueprints:
            return None
        lock.acquire()
        g.inventory_database_lock = True
        if get_startup_error() and request.blueprint != "backups":
            return jsonify(error="database_recovery_required",
                           error_code="database_recovery_required"), 503
        return None

    @app.teardown_request
    def release_database_lock(error):
        if g.pop("inventory_database_lock", False):
            lock.release()
