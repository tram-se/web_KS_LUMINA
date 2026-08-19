from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import staff_required
from accounts.models import Booking, ConsultationRequest, User

from .forms import BookingStatusForm, ConsultationStatusForm, CustomerUpdateForm


@staff_required
def staff_home(request):
    context = {
        "pending_bookings": Booking.objects.filter(
            status=Booking.Status.PENDING
        ).count(),
        "confirmed_bookings": Booking.objects.filter(
            status=Booking.Status.CONFIRMED
        ).count(),
        "new_consultations": ConsultationRequest.objects.filter(
            status=ConsultationRequest.Status.NEW
        ).count(),
        "customer_count": User.objects.filter(role=User.Role.CUSTOMER).count(),
        "recent_bookings": Booking.objects.select_related("customer")[:5],
        "recent_consultations": ConsultationRequest.objects.filter(
            status=ConsultationRequest.Status.NEW
        )[:4],
    }
    return render(request, "staff/staff_home.html", context)


@staff_required
def staff_bookings(request):
    bookings = Booking.objects.select_related("customer").all()
    status = request.GET.get("status")
    if status in Booking.Status.values:
        bookings = bookings.filter(status=status)
    return render(
        request,
        "staff/staff_bookings.html",
        {"bookings": bookings, "active_status": status},
    )


@staff_required
def staff_booking_detail(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("customer"), pk=booking_id
    )
    form = BookingStatusForm(request.POST or None, instance=booking)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Đã cập nhật đơn {booking.booking_code}.")
        return redirect("staff-booking-detail", booking_id=booking.pk)
    return render(
        request, "staff/staff_booking_detail.html", {"booking": booking, "form": form}
    )


@staff_required
def staff_customers(request):
    query = request.GET.get("q", "").strip()
    customers = User.objects.filter(role=User.Role.CUSTOMER)
    if query:
        customers = customers.filter(full_name__icontains=query) | customers.filter(
            phone_number__icontains=query
        )
    return render(
        request,
        "staff/staff_customers.html",
        {"customers": customers.distinct(), "query": query},
    )


@staff_required
def staff_customer_detail(request, customer_id):
    customer = get_object_or_404(User, pk=customer_id, role=User.Role.CUSTOMER)
    form = CustomerUpdateForm(request.POST or None, instance=customer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Đã cập nhật thông tin khách hàng.")
        return redirect("staff-customer-detail", customer_id=customer.pk)
    return render(
        request,
        "staff/staff_customer_detail.html",
        {"customer": customer, "form": form, "bookings": customer.bookings.all()[:5]},
    )


@staff_required
def staff_consultations(request):
    consultations = ConsultationRequest.objects.all()
    return render(
        request, "staff/staff_consultations.html", {"consultations": consultations}
    )


@staff_required
def staff_consultation_detail(request, consultation_id):
    consultation = get_object_or_404(ConsultationRequest, pk=consultation_id)
    form = ConsultationStatusForm(request.POST or None, instance=consultation)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Đã cập nhật yêu cầu tư vấn.")
        return redirect("staff-consultation-detail", consultation_id=consultation.pk)
    return render(
        request,
        "staff/staff_consultation_detail.html",
        {"consultation": consultation, "form": form},
    )
