def area_users(request):
    # Cung cấp người dùng hiện tại và số thông báo chưa đọc cho mọi template.
    staff_user = getattr(request, "staff_user", None)
    customer_user = getattr(request, "customer_user", None)
    notifications = None
    unread_notifications = 0
    if staff_user is not None or customer_user is not None:
        from .models import Notification

        recipient = staff_user or customer_user
        notifications = Notification.objects.filter(recipient=recipient)[:5]
        unread_notifications = Notification.objects.filter(
            recipient=recipient, is_read=False
        ).count()
    return {
        "staff_user": staff_user,
        "customer_user": customer_user,
        "header_notifications": notifications,
        "unread_notifications": unread_notifications,
    }
