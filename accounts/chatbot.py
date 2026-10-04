import re
from datetime import date, datetime, timedelta
from django.utils import timezone
from django.db.models import Exists, OuterRef, Q
from admin_panel.models import Room, RoomType, RoomPrice
from accounts.models import Booking, ChatRoom, ChatMessage, ChatbotFAQ


def normalize_text(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s/]', ' ', text)
    return text


def find_matching_room_type(user_text, room_types):
    norm = normalize_text(user_text)
    for rt in room_types:
        name_lower = rt.name.lower()
        code_lower = rt.code.lower()
        
        if name_lower in norm or code_lower in norm:
            return rt
        
        if "delux" in norm and ("delux" in name_lower or "deluxe" in name_lower):
            return rt
        if "couple" in norm and "couple" in name_lower:
            return rt
        if ("ban công" in norm or "balcony" in norm) and "ban công" in name_lower:
            return rt
        if ("thường" in norm or "standard" in norm) and "thường" in name_lower:
            return rt
            
    return None


def parse_intent(text):
    norm = normalize_text(text)

    # 1. Yêu cầu gặp nhân viên trực tiếp
    handoff_keywords = [
        "nhân viên", "tư vấn", "gặp người", "người thật", "chuyển nhân viên",
        "trực tiếp", "hỗ trợ trực tiếp", "con người", "gặp tư vấn", "gặp lễ tân",
        "lễ tân", "gặp nhân viên tư vấn"
    ]
    if any(k in norm for k in handoff_keywords):
        return "handoff_staff"

    # 2. Truy vấn trực tiếp từ bảng ChatbotFAQ trong CSDL
    active_faqs = ChatbotFAQ.objects.filter(is_active=True)
    for faq in active_faqs:
        kw_list = [k.strip().lower() for k in faq.keywords.split(",") if k.strip()]
        if any(kw in norm for kw in kw_list):
            return faq.category.lower()

    # Fallback cho chào hỏi
    greeting_keywords = ["chào", "hi", "hello", "xin chào", "lumina ơi", "bạn là ai", "alo"]
    if any(k in norm for k in greeting_keywords) and len(norm.split()) <= 4:
        return "greeting"

    return "fallback"


def generate_bot_response(room, user_text):
    """
    Truy vấn trực tiếp dữ liệu từ bảng ChatbotFAQ và các bảng CSDL Room / RoomType.
    """
    intent = parse_intent(user_text)

    # TH1: Chuyển sang Nhân viên tư vấn
    if intent == "handoff_staff":
        room.mode = ChatRoom.Mode.STAFF
        room.save(update_fields=['mode', 'updated_at'])
        reply = (
            "Dạ, Lumina đã chuyển cuộc trò chuyện đến nhân viên tư vấn. "
            "Quý khách vui lòng chờ một lát. Nếu cần gấp, vui lòng gọi "
            "07754169690 để được trả lời nhanh nhất."
        )
        return reply, True

    room_types = RoomType.objects.filter(is_active=True, listing_status=RoomType.ListingStatus.PUBLISHED).prefetch_related('amenities', 'prices')

    # TH2: Kiểm tra phòng trống (Truy vấn CSDL Room thời gian thực)
    if intent == "availability":
        date_match = re.search(
            r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{4}))?", user_text
        )
        requested_date = date.today()
        if date_match:
            try:
                requested_date = date(
                    int(date_match.group(3) or requested_date.year),
                    int(date_match.group(2)),
                    int(date_match.group(1)),
                )
            except ValueError:
                requested_date = date.today()
        has_requested_date = date_match is not None
        checkout_date = requested_date + timedelta(days=1)
        date_str_info = f" ngày {requested_date:%d/%m/%Y}"

        available_rooms = Room.objects.filter(
            room_type__is_active=True,
            room_type__is_under_maintenance=False,
        )
        if has_requested_date:
            overlap = Booking.objects.filter(
                Q(room=OuterRef("pk"))
                | Q(room_assignments__room=OuterRef("pk")),
                check_in__lt=checkout_date,
                check_out__gt=requested_date,
            ).exclude(status=Booking.Status.CANCELLED)
            available_rooms = available_rooms.filter(
                status__in=(
                    Room.Status.AVAILABLE,
                    Room.Status.DEPOSIT,
                    Room.Status.BOOKED,
                )
            ).annotate(has_overlap=Exists(overlap)).filter(has_overlap=False)
        else:
            available_rooms = available_rooms.filter(status=Room.Status.AVAILABLE)
        available_rooms = available_rooms.select_related("room_type")

        count = available_rooms.count()
        if count > 0:
            type_counts = {}
            for r in available_rooms:
                tname = r.room_type.name
                type_counts[tname] = type_counts.get(tname, 0) + 1
            
            lines = [
                f"✨ **Bảng tình trạng phòng trống tại Lumina ({date_str_info}):**\n",
                "| Hạng phòng | Sức chứa | Giá / Đêm | Số phòng còn trống | Tình trạng |",
                "| :--- | :--- | :--- | :--- | :--- |"
            ]
            for rt in room_types:
                c = type_counts.get(rt.name, 0)
                if c > 0:
                    price_obj = rt.prices.filter(is_active=True).first()
                    price_val = f"{price_obj.price:,.0f} VNĐ" if price_obj else "450.000 VNĐ"
                    lines.append(f"| {rt.name} | {rt.max_guests} khách | {price_val} | **{c} phòng** | Sẵn sàng đón khách |")
            
            lines.append(f"\n👉 Tổng cộng đang có **{count} phòng trống sẵn sàng**. Quý khách có thể bấm **Đặt phòng ngay** để giữ phòng ạ!")
            reply = "\n".join(lines)
        else:
            reply = f"Dạ hiện tại các phòng vào{date_str_info} đang kín lịch. Quý khách vui lòng chọn ngày khác hoặc bấm **[👨‍💼 Gặp nhân viên tư vấn]** để Lễ tân hỗ trợ ạ!"
        return reply, False

    # TH3: Bảng giá phòng (Truy vấn CSDL RoomPrice thời gian thực)
    if intent == "pricing":
        lines = [
            "💰 **Bảng giá Niêm yết các Hạng phòng tại Khách sạn Lumina:**\n",
            "| Hạng phòng | Sức chứa | Giá / Đêm | Ghi chú |",
            "| :--- | :--- | :--- | :--- |"
        ]
        for rt in room_types:
            price_obj = rt.prices.filter(is_active=True).first()
            price_val = f"{price_obj.price:,.0f} VNĐ" if price_obj else "Liên hệ Lễ tân"
            lines.append(f"| {rt.name} | {rt.max_guests} khách | {price_val} | Đã gồm ăn sáng |")
        
        lines.append("\n✨ *Giá phòng đã bao gồm ăn sáng buffet, internet tốc độ cao & nước uống miễn phí.*")
        lines.append("👉 Quý khách chọn hạng phòng và bấm **Đặt phòng** để nhận ưu đãi!")
        reply = "\n".join(lines)
        return reply, False

    # TH4: Kiểm tra truy vấn từ bảng ChatbotFAQ trong CSDL
    faq_match = ChatbotFAQ.objects.filter(category__iexact=intent, is_active=True).first()
    if faq_match:
        return faq_match.answer, False

    # TH5: Lời chào
    if intent == "greeting":
        reply = (
            "Dạ em chào Quý khách! 👋 Em là **Lumina Chatbot** - Trợ lý hỗ trợ tự động của Khách sạn Lumina 🏨.\n\n"
            "Em có thể giải đáp nhanh thông tin từ CSDL cho Quý khách:\n"
            "• Xem Bảng giá & Tiện ích các hạng phòng (Deluxe, Couple, Ban công...)\n"
            "• Kiểm tra số lượng phòng trống theo ngày\n"
            "• Hướng dẫn Đặt phòng & Thanh toán MoMo / Ngân hàng\n"
            "• Kết nối với Nhân viên tư vấn Lễ tân\n\n"
            "Quý khách cần em hỗ trợ câu hỏi nào ạ? ❤️"
        )
        return reply, False

    # TH Fallback
    reply = (
        "Dạ, câu hỏi này cần nhân viên Lumina hỗ trợ thêm. Vui lòng chờ một lát, "
        "nhân viên sẽ trả lời trong chat. Nếu cần gấp, vui lòng gọi "
        "07754169690 để được trả lời nhanh nhất."
    )
    return reply, False
