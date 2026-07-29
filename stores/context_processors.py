def owner_store(request):
    """Makes the logged-in owner's store available in every template (for nav)."""
    if request.user.is_authenticated and getattr(request.user, "is_owner_role", False):
        store = request.user.stores.first()
        return {"nav_owner_store": store}
    return {}
