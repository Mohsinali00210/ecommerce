from django.core.management.base import BaseCommand, CommandError

from couriers.models import CourierCredential, CourierProvider, ShipperProfile


class Command(BaseCommand):
    help = ("Save courier API credentials (encrypted) and optionally your pickup/return address. "
            "Example: manage.py courier_setup leopards --env sandbox --key KEY --password PASS")

    def add_arguments(self, parser):
        parser.add_argument("provider_code")
        parser.add_argument("--env", choices=["sandbox", "live"], default="sandbox")
        parser.add_argument("--key", required=True)
        parser.add_argument("--password", required=True)
        parser.add_argument("--use", action="store_true", help="Switch the courier to this environment")
        parser.add_argument("--shipper-name")
        parser.add_argument("--shipper-phone")
        parser.add_argument("--shipper-email", default="")
        parser.add_argument("--shipper-address")
        parser.add_argument("--shipper-city")

    def handle(self, provider_code, **o):
        p = CourierProvider.objects.filter(code=provider_code).first()
        if not p:
            raise CommandError(f"No courier with code '{provider_code}'")
        cred, created = CourierCredential.objects.update_or_create(
            provider=p, environment=o["env"], label="Main account",
            defaults={"api_key": o["key"], "api_password": o["password"], "is_active": True})
        if o["use"]:
            p.environment = o["env"]
            p.save(update_fields=["environment"])
        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Updated'} {o['env']} credentials for {p.name}."))
        if o.get("shipper_name"):
            missing = [k for k in ("shipper_phone", "shipper_address", "shipper_city") if not o.get(k)]
            if missing:
                raise CommandError("Also pass: " + ", ".join("--" + m.replace("_", "-") for m in missing))
            sh = ShipperProfile.default() or ShipperProfile(is_default=True)
            sh.contact_name, sh.phone, sh.email = o["shipper_name"], o["shipper_phone"], o["shipper_email"]
            sh.address, sh.city = o["shipper_address"], o["shipper_city"]
            sh.is_default = True
            sh.save()
            self.stdout.write(self.style.SUCCESS(f"Saved pickup/return details: {sh}"))
