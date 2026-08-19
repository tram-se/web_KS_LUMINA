# Website Khach san Lumina - Phase 1

Phase 1 includes Django initialization, MySQL configuration, custom user authentication, and role-based access control.

## Roles

- `CUSTOMER`: self-registration and customer area.
- `STAFF`: staff area; create accounts through Django Admin.
- `ADMIN`: admin area and Django Admin account management.

## Local setup

1. Install Python 3.12+ and MySQL 8+.
2. Create a MySQL database and user:

```sql
CREATE DATABASE lumina_hotel CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'lumina_user'@'localhost' IDENTIFIED BY 'change-this-password';
GRANT ALL PRIVILEGES ON lumina_hotel.* TO 'lumina_user'@'localhost';
FLUSH PRIVILEGES;
```

3. Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

4. Set the variables from `.env.example` in the shell or your IDE launch configuration.
5. Run migrations and create the first administrator:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/dang-ky/` or `http://127.0.0.1:8000/admin/`.

The project deliberately stops at Phase 1. Room booking, staff operations, and full hotel administration are reserved for later phases.

## Module structure

```text
accounts/
	forms.py       Customer registration
	views.py       Login, logout, dashboard and customer entry point
	urls.py        Authentication and customer URLs
	decorators.py  Role protection shared by all modules
	models.py      Custom User and current booking/consultation schema

staff/
	views.py       Staff dashboard, bookings, customers and consultations
	forms.py       Staff processing forms
	urls.py        Staff URLs under /staff/
	apps.py        Staff app configuration

admin_panel/
	views.py       Admin landing page
	models.py      Room, room type, pricing, amenity, service and activity log
	admin.py       Django Admin registrations and CRUD configuration
	signals.py     Automatic system activity logging
	urls.py        Admin panel URLs under /admin-panel/

templates/accounts/       Authentication and customer templates
templates/staff/          Staff workspace templates
templates/admin_panel/    Admin landing template
```

The booking and consultation model classes remain in `accounts/models.py` for migration compatibility with the existing Phase 1 database. Staff owns their views, forms, URLs, and templates; this keeps the feature boundary separate without renaming existing database migration state.

## Independent area sessions

The three account areas use separate session identities:

- Admin uses Django's standard `_auth_user_id` through `/admin/`.
- Staff uses `staff_user_id` through `/staff/dang-nhap/` and `/staff/dang-xuat/`.
- Customer uses `customer_user_id` through `/dang-nhap/` and `/dang-xuat/`.

Staff and Customer login never call Django's global `login()` function, so they cannot replace or log out an Admin session in the same browser. Their role decorators read `request.staff_user` and `request.customer_user`; access to `/staff/` and `/customer/` is therefore isolated by both session key and role.

The Admin workspace is available at `/admin-panel/`. It provides dashboard links for user roles, customers, staff, bookings, room types, rooms, room pricing by effective dates, amenities, services, room status, and activity logs. Django Admin at `/admin/` remains available for full CRUD operations.
