from enum import Enum
from textwrap import dedent


class Country(Enum):
    SOUTH_AFRICA = "South Africa"
    KENYA = "Kenya"
    ZAMBIA = "Zambia"
    FRANCE = "France"
    ARGENTINA = "Argentina"
    HONDURAS = "Honduras"
    UNSPECIFIED = "Unspecified"


def get_country_from_string(country: str) -> Country:
    """
    Get the country enum from a string.
    Matches on the value or the name of the enum.
    :param country:
    :return:
    """
    for c in Country:
        if c.value.lower() == country.lower() or c.name.lower() == country.lower():
            return c
    return Country.UNSPECIFIED


def get_country_glossary(country: Country) -> str | None:
    """
    Get the glossary for a specific country
    :param country:
    :return:
    """
    return _GLOSSARY.get(country, None)


# A glossary of terms that may be used to contextualize tasks
# eventually this could move to a file or database
_GLOSSARY = {
    Country.SOUTH_AFRICA:
        dedent("""\
        Hustler - Hard working person who does odd jobs to make ends meet (small and micro businesses).
        GDE Brigade - Gauteng Department of Education (GDE) Brigade was a short-term programme for contract workers in the education sector.
        Kotas - A South African street food. 
        Bunny chow - Indian South African fast food dish.
        Crew Member - A member of a team but not necessarily in the aviation industry.
        Ambassador - A person who works ta public relation of a company.
        Braider - A person who specializes in creating beautiful African hairstyles.
        """),
    Country.KENYA:
        dedent("""\
        Muuguzi - Nurse.
        Dokta - Doctor.
        Mhasibu - Accountant / Bookkeeper.
        Karani - Clerk / Office worker.
        Mwal - Teacher.
        Makani - Engineer.
        Rubani - Pilot.
        Nahodha - Captain.
        Kiongozi - Leader / Manager.
        Mkufunzi - Trainer / Coach.
        Mhudumu - Attendant / Tour guide.
        Hustler - Hard working person who does odd jobs to make ends meet (small and micro businesses).
        Casual - Works for a day/task and is paid on completion of the task or at the end of the day.
        Mama mboga - Vegetable seller.
        Mchuuzi / Hawker - A street vendor, informal trader.
        Kibarua - Laborer / General worker.
        Fundi mchundo - Handyman / Odd jobs person.
        Muuzaji - Salesperson / Street vendor.
        Mwenye Duka - Small shop owner.
        Msee wa Mjengo - Builder / Mason (informal construction).
        Mshonaji - Tailor / Seamstress.
        Boda Boda - A motorcycle taxi.
        Nduthi - A motorcycle taxi.
        Tuk tuk - A 3-wheeler taxi.
        Makanga - A conductor of a matatu.
        Matatu - The main public transport it is private sector owned.
        Mathree / Ma3 - Matatu.
        Dereva - Driver.
        Askari - A security guard.
        Mlinzi - Watchman / Security guard.
        Housegirl - A housekeeper/ nanny.
        Auntie - Domestic Worker / Housekeeper/ nanny.
        Fundi - Technician / Skilled Worker / artisan.
        Fundi wa Gari / Mech - A mechanic.
        Makanika - Mechanic.
        Seremala - Carpenter.
        Kinyozi / Barber.
        Saloonist / Stylist / Braider - hairdresser.
        Mpishi - Cook.
        Msanii - Artist (musician, actor etc).
        Mziki - Music.
        Mwanamuziki - Musician.
        Mchezaji - Player / Athlete / Performer.
        Mkulima - Farmer.
        Shamba Boy / Shamba Girl - A farm worker.
        Mpesa agent - Assist customers with the use of m-pesa services, receive deposits and give cash.
        Kiosk - A small shop that sells household essentials in small quantities e.g. soap, bread etc.
        Cyber - An internet café where people go to access computers with internet, printing services and technical assistance in accessing digital government services for a fee.
        Mjengo - A construction site often used to refer to a place where manual labour is needed/performed.
        Mtu wa mkono - Used in construction sites, it is the assistants who are usually employed to help the skilled workers (masons, painters etc).
        Mchukuaji mizigo - Porter / Loader.
        Jua Kali - Informal sector of traders and businesses (it is the general term used for Kenya's informal sector ranging from furniture making, pots, pans, autoparts, handicrafts etc.
        Choma - Roasted.
        Nyama - Meat.
        Nyama choma - Roasted meat.
        Ugali / Sembe - A staple food in Kenya made from maize flour.
        Mpesa - A mobile money transfer service.
        Kanairo - Nairobi.
        Ocha - Village.
        Mtaa - Neighbourhood, refers to a specific area in the city.
        Wathii - Market.
        Mtumba - Second hand clothes.
        """),
    Country.ZAMBIA:
        dedent("""\
        Hustler - Hard working person who does odd jobs to make ends meet (small and micro businesses).
        Casual - Works for a day/task and is paid on completion of the task or at the end of the day.
        Tuntufye / Vendor - A street vendor or informal trader.
        Kaloba - Informal money lending or borrowing.
        Kateka - Small business owner / entrepreneur.
        Minibus conductor - Collects fares on a minibus (similar to matatu conductor in Kenya).
        Kabaza - A bicycle taxi.
        Motor bike / Bajaj - A motorcycle or 3-wheeler taxi.
        Chikanda - A Zambian food made from orchid tubers (local staple).
        Nshima - The main staple food in Zambia, made from maize flour (similar to ugali).
        Relish - Any side dish eaten with nshima (vegetables, fish, meat).
        Garden - A small plot of land used for subsistence farming.
        Compound - A high-density residential area / township (e.g., Chibolya, Matero in Lusaka).
        Lusaka - Capital city of Zambia, main economic hub.
        Copperbelt - Major industrial region in Zambia known for copper mining (cities: Kitwe, Ndola).
        Shoprite / Game - Major retail chain stores in Zambia.
        Airtel Money / MTN Money - Mobile money transfer services in Zambia.
        NAPSA - National Pension Scheme Authority (mandatory pension contributions).
        NHIMA - National Health Insurance Management Authority (health insurance).
        TEVETA - Technical Education, Vocational and Entrepreneurship Training Authority (vocational training body).
        UNZA - University of Zambia (main public university in Lusaka).
        CBU - Copperbelt University (main public university in the Copperbelt).
        ZESCO - Zambia Electricity Supply Corporation (national power utility).
        Zambeef - Major Zambian food and agribusiness company.
        Fitter - A skilled artisan / maintenance mechanic (common in mining and industry).
        Piece work / Piece job - Casual or temporary work paid per task completed.
        """),
    Country.ARGENTINA:
        dedent("""\
        Changas - Small jobs, gigs, tasks
        Mozo/a - Waiter/Waitress
        En negro - Informal work, often without contracts
        Bachero/a - Cleans dishes in a kitchen
        Kiosco/Kiosquero - Kiosk/Shopkeeper
        YPF - Argentine oil energy company
        TecnoMorris - Technology company
        Fiambrería - Deli
        Pasantía - Internship
        Remisería/Remisera - Remisero (private hire car driver)
        Parrilla - Grill
        Verdulería - Green grocery
        """),
    Country.HONDURAS:
        dedent("""\
        Chamba - A job or gig
        Pulpería / Pulpero(a) - Small neighbourhood corner shop / its shopkeeper
        Maquila - Export assembly factory, mostly textiles and apparel (common in the Sula Valley)
        Operario(a) de maquila - Production line worker in a maquila
        Agente de call center - Customer service agent in a call center, often bilingual (Spanish/English)
        Jornalero(a) - Day labourer, e.g. on coffee, banana, melon or palm farms
        Mototaxi - Motorcycle taxi
        Cobrador(a) - Fare collector on a bus or "rapidito" (minibus)
        Baleadas - Popular Honduran street food; "baleadera" is a woman who makes and sells them
        Décimo tercer mes / Décimo cuarto mes - Mandatory extra month's salary paid in December / June
        INFOP - National vocational training institute (Instituto Nacional de Formación Profesional)
        """),
}
