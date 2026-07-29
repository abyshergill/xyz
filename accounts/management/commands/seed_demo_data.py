from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import CustomerProfile, OwnerProfile, User


class Command(BaseCommand):
    help = (
        "Creates dummy demo accounts for quick local testing: a Platform "
        "Admin, a Store Owner (with no store yet, ready to create one), and "
        "a Customer. Safe to run multiple times -- existing accounts are "
        "left untouched and their credentials are just reprinted."
    )

    DEMO_ACCOUNTS = [
        {
            "username": "admin_demo",
            "email": "admin_demo@example.com",
            "password": "Admin@12345",
            "role": User.Role.ADMIN,
            "is_staff": True,
            "is_superuser": True,
            "label": "Platform Admin",
        },
        {
            "username": "owner_demo",
            "email": "owner_demo@example.com",
            "password": "Owner@12345",
            "role": User.Role.OWNER,
            "is_staff": False,
            "is_superuser": False,
            "label": "Store Owner (no store yet -- log in and you'll be sent straight to 'Create Your Store')",
        },
        {
            "username": "customer_demo",
            "email": "customer_demo@example.com",
            "password": "Customer@12345",
            "role": User.Role.CUSTOMER,
            "is_staff": False,
            "is_superuser": False,
            "label": "Customer",
        },
    ]

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding demo accounts...\n"))

        for account in self.DEMO_ACCOUNTS:
            user, created = User.objects.get_or_create(
                username=account["username"],
                defaults={
                    "email": account["email"],
                    "role": account["role"],
                    "is_staff": account["is_staff"],
                    "is_superuser": account["is_superuser"],
                },
            )
            if created:
                user.set_password(account["password"])
                user.save()
                if account["role"] == User.Role.CUSTOMER:
                    CustomerProfile.objects.get_or_create(
                        user=user,
                        defaults={
                            "address": "123 Demo Street",
                            "province": "Demo Province",
                            "pincode": "00000",
                            "country": "Demoland",
                        },
                    )
                elif account["role"] == User.Role.OWNER:
                    OwnerProfile.objects.get_or_create(user=user)
                status = self.style.SUCCESS("created")
            else:
                status = self.style.WARNING("already exists")

            self.stdout.write(
                f"  [{status}] {account['label']}\n"
                f"      username: {account['username']}\n"
                f"      password: {account['password']}\n"
            )

        self.stdout.write(self.style.MIGRATE_HEADING("\nDone. Log in at /accounts/login/"))
        self.stdout.write(
            "  - admin_demo    -> platform admin dashboard (/platform-admin/dashboard/)\n"
            "  - owner_demo    -> will be redirected to create your own stall (/owner/store/create/)\n"
            "  - customer_demo -> browse stalls and place orders\n"
        )
