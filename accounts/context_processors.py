def area_users(request):
    return {
        "staff_user": getattr(request, "staff_user", None),
        "customer_user": getattr(request, "customer_user", None),
    }
