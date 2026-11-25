"""Weight-based shipping charges (what the customer pays).

    zone    within city       destination city == origin city
            Zone A            same province as the origin
            Zone B            any other province (also used when the province is unknown)
    weight  the slab whose max_grams is the first >= parcel weight; heavier parcels pay the
            heaviest slab + `extra` for every started `extra_step_grams` above it.

Province: the address's state/province field when it names a province, otherwise the city
is looked up in CITY_PROVINCE below.
"""
import math
from decimal import Decimal

from .models import ShippingTariff, ShippingZone, ShipperProfile, normalize_city

ZERO = Decimal("0.00")

PROVINCE_NAMES = {
    "punjab": "Punjab",
    "sindh": "Sindh",
    "khyber pakhtunkhwa": "Khyber Pakhtunkhwa",
    "balochistan": "Balochistan",
    "islamabad": "Islamabad Capital Territory",
    "gilgit baltistan": "Gilgit-Baltistan",
    "azad kashmir": "Azad Jammu & Kashmir",
}
_PROVINCE_ALIASES = {
    "punjab": "punjab", "pb": "punjab", "pjb": "punjab",
    "sindh": "sindh", "sind": "sindh",
    "khyberpakhtunkhwa": "khyber pakhtunkhwa", "kpk": "khyber pakhtunkhwa", "kp": "khyber pakhtunkhwa",
    "nwfp": "khyber pakhtunkhwa", "khyberpakhtoonkhwa": "khyber pakhtunkhwa", "pakhtunkhwa": "khyber pakhtunkhwa",
    "balochistan": "balochistan", "baluchistan": "balochistan", "blochistan": "balochistan",
    "islamabad": "islamabad", "ict": "islamabad", "islamabadcapitalterritory": "islamabad",
    "federal": "islamabad", "federalcapital": "islamabad",
    "gilgitbaltistan": "gilgit baltistan", "gb": "gilgit baltistan", "northernareas": "gilgit baltistan",
    "azadkashmir": "azad kashmir", "ajk": "azad kashmir", "azadjammuandkashmir": "azad kashmir",
    "azadjammukashmir": "azad kashmir", "kashmir": "azad kashmir",
}
_CITIES = {
    "punjab": "lahore faisalabad rawalpindi gujranwala multan sialkot bahawalpur sargodha sheikhupura jhang "
              "rahimyarkhan gujrat kasur sahiwal okara wahcantonment deraghazikhan dgkhan "
              "chiniot kamoke hafizabad sadiqabad burewala khanewal muzaffargarh mandibahauddin jhelum "
              "khanpur pakpattan daska gojra muridke bahawalnagar vehari attock chakwal mianwali bhakkar "
              "layyah lodhran narowal nankanasahib tobateksingh khushab rajanpur taxila "
              "wazirabad kharian murree arifwala chishtian haroonabad jaranwala samundri kotaddu "
              "pattoki raiwind shakargarh talagang pindigheb fortabbas kamalia ahmedpureast",
    "sindh": "karachi hyderabad sukkur larkana nawabshah shaheedbenazirabad mirpurkhas jacobabad shikarpur "
             "khairpur dadu thatta badin tandoadam tandoallahyar umerkot sanghar ghotki kashmore kandhkot "
             "matiari jamshoro kotri moro mehar sehwan naushahroferoze qambar kambar mithi tharparkar "
             "hala tandomuhammadkhan",
    "khyber pakhtunkhwa": "peshawar mardan mingora swat abbottabad kohat dikhan deraismailkhan bannu "
                          "mansehra nowshera charsadda swabi haripur chitral timergara lakkimarwat karak "
                          "hangu tank batkhela dargai parachinar landikotal bajaur khyber malakand "
                          "battagram shangla buner upperdir lowerdir dir risalpur tarbela",
    "balochistan": "quetta turbat khuzdar hub chaman gwadar sibi zhob loralai "
                   "deramuradjamali dalbandin kharan nushki pishin mastung kalat "
                   "ustamuhammad panjgur jaffarabad nasirabad lasbela uthal",
    "islamabad": "islamabad",
    "gilgit baltistan": "gilgit skardu hunza chilas ghizer ghanche astore nagar aliabad khaplu",
    "azad kashmir": "muzaffarabad mirpur kotli bhimber rawalakot bagh pallandri hajira hattian neelum "
                    "dadyal",
}
CITY_PROVINCE = {}
for _prov, _names in _CITIES.items():
    for _c in _names.split():
        CITY_PROVINCE[normalize_city(_c)] = _prov


def normalize_province(value):
    """'KPK' / 'Khyber Pakhtunkhwa' / 'kp' -> 'khyber pakhtunkhwa' (None when unknown)."""
    return _PROVINCE_ALIASES.get(normalize_city(value)) if value else None


def province_of(city, state=""):
    return normalize_province(state) or CITY_PROVINCE.get(normalize_city(city))


def province_label(key):
    return PROVINCE_NAMES.get(key or "", "")


def grams_of(weight_kg):
    """Product.weight is stored in kg."""
    try:
        return max(0, int((Decimal(weight_kg or 0) * 1000).to_integral_value()))
    except Exception:
        return 0


def origin(tariff):
    city = tariff.origin_city
    if not city:
        shipper = ShipperProfile.default()
        city = shipper.city if shipper else ""
    prov = normalize_province(tariff.origin_province) or CITY_PROVINCE.get(normalize_city(city))
    return city, prov


def zone_for(tariff, city, state=""):
    """Zone for a destination. No city -> None (caller shows an estimate)."""
    if not city:
        return None
    o_city, o_prov = origin(tariff)
    if o_city and normalize_city(o_city) == normalize_city(city):
        return ShippingZone.WITHIN_CITY
    dest_prov = province_of(city, state)
    if o_prov and dest_prov and o_prov == dest_prov:
        return ShippingZone.SAME_PROVINCE
    return ShippingZone.OTHER_PROVINCE


def _slabs(tariff):
    return sorted(tariff.slabs.all(), key=lambda s: s.max_grams)


def charge(tariff, grams, zone):
    """Shipping charge for one parcel of `grams` to `zone` (None zone = Zone B, the highest)."""
    grams = int(grams or 0)
    if grams <= 0:
        return ZERO
    zone = zone or ShippingZone.OTHER_PROVINCE
    slabs = _slabs(tariff)
    if not slabs:
        return ZERO
    for s in slabs:
        if grams <= s.max_grams:
            return s.price_for(zone)
    last = slabs[-1]
    step = max(1, tariff.extra_step_grams or 1)
    steps = math.ceil((grams - last.max_grams) / step)
    return last.price_for(zone) + tariff.extra_for(zone) * steps


def all_zone_charges(tariff, grams):
    """{zone: charge} for the product page table."""
    return {z.value: charge(tariff, grams, z) for z in ShippingZone}


def browser_table(tariff, zone):
    """Data the cart page's JavaScript needs to repeat charge() for one zone."""
    zone = zone or ShippingZone.OTHER_PROVINCE
    return {
        "slabs": [[s.max_grams, float(s.price_for(zone))] for s in _slabs(tariff)],
        "step": max(1, tariff.extra_step_grams or 1),
        "extra": float(tariff.extra_for(zone)),
    }


def default_tariff():
    return ShippingTariff.default()
