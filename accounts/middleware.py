from .models import User


class AreaSessionMiddleware:
    """Loads Staff and Customer identities without touching Django's admin auth key."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.staff_user = self._load_user(request, "staff_user_id", User.Role.STAFF)
        request.customer_user = self._load_user(
            request, "customer_user_id", User.Role.CUSTOMER
        )
        return self.get_response(request)

    @staticmethod
    def _load_user(request, session_key, role):
        user_id = request.session.get(session_key)
        if not user_id:
            return None
        try:
            user = User.objects.get(pk=user_id, role=role, is_active=True)
        except User.DoesNotExist:
            request.session.pop(session_key, None)
            return None
        return user
