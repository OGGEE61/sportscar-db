import math


CITY_TO_REGION = {
    'Warszawa': 'PL-MZ', 'Kraków': 'PL-MA', 'Łódź': 'PL-LD', 'Wrocław': 'PL-DS',
    'Poznań': 'PL-WP', 'Gdańsk': 'PL-PM', 'Szczecin': 'PL-ZP', 'Bydgoszcz': 'PL-KP',
    'Lublin': 'PL-LU', 'Białystok': 'PL-PD', 'Katowice': 'PL-SL', 'Gdynia': 'PL-PM',
    'Częstochowa': 'PL-SL', 'Radom': 'PL-MZ', 'Toruń': 'PL-KP', 'Sosnowiec': 'PL-SL',
    'Kielce': 'PL-SK', 'Rzeszów': 'PL-PK', 'Gliwice': 'PL-SL', 'Zabrze': 'PL-SL',
    'Olsztyn': 'PL-WN', 'Bielsko-Biała': 'PL-SL', 'Bytom': 'PL-SL', 'Zielona Góra': 'PL-LB',
    'Rybnik': 'PL-SL', 'Ruda Śląska': 'PL-SL', 'Tychy': 'PL-SL', 'Gorzów Wielkopolski': 'PL-LB',
    'Dąbrowa Górnicza': 'PL-SL', 'Płock': 'PL-MZ', 'Elbląg': 'PL-WN', 'Opole': 'PL-OP',
    'Wałbrzych': 'PL-DS', 'Włocławek': 'PL-KP', 'Tarnów': 'PL-MA', 'Chorzów': 'PL-SL',
    'Koszalin': 'PL-ZP', 'Kalisz': 'PL-WP', 'Legnica': 'PL-DS', 'Grudziądz': 'PL-KP',
    'Jaworzno': 'PL-SL', 'Słupsk': 'PL-ZP', 'Jastrzębie-Zdrój': 'PL-SL', 'Nowy Sącz': 'PL-MA',
    'Jelenia Góra': 'PL-DS', 'Siedlce': 'PL-MZ', 'Mysłowice': 'PL-SL', 'Konin': 'PL-WP',
    'Piła': 'PL-WP', 'Piotrków Trybunalski': 'PL-LD', 'Łomianki': 'PL-MZ', 'Ociąż': 'PL-WP',
    'Opalenica': 'PL-WP', 'Leszno': 'PL-WP', 'Ornontowice': 'PL-SL', 'Pabianice': 'PL-LD',
    'Szamocin': 'PL-WP', 'Kazuń Polski': 'PL-MZ', 'Niepołomice': 'PL-MA', 'Nowy Dwór Gdański': 'PL-PM',
    'Piaseczno': 'PL-MZ', 'Pruszków': 'PL-MZ', 'Marki': 'PL-MZ', 'Ząbki': 'PL-MZ',
    'Otwock': 'PL-MZ', 'Legionowo': 'PL-MZ', 'Wołomin': 'PL-MZ', 'Sopot': 'PL-PM',
    'Wejherowo': 'PL-PM', 'Rumia': 'PL-PM', 'Starogard Gdański': 'PL-PM', 'Tczew': 'PL-PM',
    'Lubin': 'PL-DS', 'Głogów': 'PL-DS', 'Świdnica': 'PL-DS', 'Bolesławiec': 'PL-DS',
    'Inowrocław': 'PL-KP', 'Świecie': 'PL-KP', 'Brodnica': 'PL-KP', 'Chełm': 'PL-LU',
    'Zamość': 'PL-LU', 'Biała Podlaska': 'PL-LU', 'Puławy': 'PL-LU', 'Nowa Sól': 'PL-LB',
    'Żary': 'PL-LB', 'Zgierz': 'PL-LD', 'Skierniewice': 'PL-LD', 'Radomsko': 'PL-LD',
    'Kutno': 'PL-LD', 'Bełchatów': 'PL-LD', 'Oświęcim': 'PL-MA', 'Chrzanów': 'PL-MA',
    'Olkusz': 'PL-MA', 'Zakopane': 'PL-MA', 'Kędzierzyn-Koźle': 'PL-OP', 'Nysa': 'PL-OP',
    'Brzeg': 'PL-OP', 'Mielec': 'PL-PK', 'Przemyśl': 'PL-PK', 'Stalowa Wola': 'PL-PK',
    'Krosno': 'PL-PK', 'Jasło': 'PL-PK', 'Suwałki': 'PL-PD', 'Łomża': 'PL-PD',
    'Augustów': 'PL-PD', 'Siemianowice Śląskie': 'PL-SL', 'Tarnowskie Góry': 'PL-SL',
    'Piekary Śląskie': 'PL-SL', 'Racibórz': 'PL-SL', 'Zawiercie': 'PL-SL', 'Wodzisław Śląski': 'PL-SL',
    'Mikołów': 'PL-SL', 'Cieszyn': 'PL-SL', 'Żywiec': 'PL-SL', 'Ostrowiec Świętokrzyski': 'PL-SK',
    'Starachowice': 'PL-SK', 'Skarżysko-Kamienna': 'PL-SK', 'Sandomierz': 'PL-SK',
    'Ełk': 'PL-WN', 'Iława': 'PL-WN', 'Giżycko': 'PL-WN', 'Ostróda': 'PL-WN',
    'Ostrów Wielkopolski': 'PL-WP', 'Gniezno': 'PL-WP', 'Września': 'PL-WP', 'Swarzędz': 'PL-WP',
    'Stargard': 'PL-ZP', 'Kołobrzeg': 'PL-ZP', 'Świnoujście': 'PL-ZP', 'Szczecinek': 'PL-ZP',
    'Balice': 'PL-MA', 'Dobrzań': 'PL-ZP', 'Góra': 'PL-DS', 'Halinów': 'PL-MZ',
    'Golęczewo': 'PL-WP', 'Aleksandrów': 'PL-LD', 'Aleksandrów Łódzki': 'PL-LD',
    'Czarna': 'PL-PK', 'Stanisławów Pierwszy': 'PL-MZ', 'Garwolin': 'PL-MZ',
    'Węgrzce': 'PL-MA', 'Sochaczew': 'PL-MZ',
    'Miastko': 'PL-PM', 'Stare Bielice': 'PL-ZP', 'Ozimek': 'PL-OP', 'Sokołów Podlaski': 'PL-MZ',
    'Świdwin': 'PL-ZP', 'Trzebiesławice': 'PL-SL', 'Kamionki': 'PL-WP', 'Gowidlino': 'PL-PM',
    'Tłuszcz': 'PL-MZ', 'Góra Kalwaria': 'PL-MZ', 'Przygodzice': 'PL-WP', 'Parsęcko': 'PL-ZP',
    'Wieruszów': 'PL-LD', 'Staszów': 'PL-SK', 'Radzymin': 'PL-MZ', 'Jawczyce': 'PL-MZ',
    'Nowy Secymin': 'PL-MZ', 'Luboń': 'PL-WP', 'Suchożebry': 'PL-MZ', 'Bielewo': 'PL-WP',
    'Nowy Targ': 'PL-MA', 'Nowe Miasto nad Pilicą': 'PL-MZ', 'Bieruń': 'PL-SL',
    'Ciężkowice': 'PL-MA', 'Zwoleń': 'PL-MZ', 'Podkowa Leśna': 'PL-MZ',
    'Czeladź': 'PL-SL', 'Straszyn': 'PL-PM', 'Wróblew': 'PL-LD', 'Syców': 'PL-DS',
    'Trzebinia': 'PL-MA', 'Świdnik': 'PL-LU', 'Opatów': 'PL-SK', 'Księżyno': 'PL-PD',
    'Skoczów': 'PL-SL', 'Izabelin C': 'PL-MZ', 'Dulowa': 'PL-MA', 'Dębica': 'PL-PK',
    'Kobiele Wielkie': 'PL-LD', 'Raków Duży': 'PL-LD', 'Krapkowice': 'PL-OP', 'Kobyłka': 'PL-MZ',
    'Międzyrzecz': 'PL-LB', 'Śrem': 'PL-WP', 'Jawiszowice': 'PL-MA', 'Rąbień': 'PL-LD',
    'Czchów': 'PL-MA', 'Michałowice': 'PL-MZ', 'Płońsk': 'PL-MZ', 'Słupca': 'PL-WP',
    'Trzebnica': 'PL-DS', 'Lipka': 'PL-WP', 'Medynia Głogowska': 'PL-PK', 'Nowe Arciszewo': 'PL-MZ',
    'Bochnia': 'PL-MA', 'Koło': 'PL-WP', 'Szczytno': 'PL-WN', 'Chwaszczyno': 'PL-PM',
    'Rabka-Zdrój': 'PL-MA', 'Czernica': 'PL-DS', 'Kosakowo': 'PL-PM', 'Lubliniec': 'PL-SL',
    'Lubicz Dolny': 'PL-KP', 'Kępno': 'PL-WP', 'Szubin': 'PL-KP', 'Magdalenka': 'PL-MZ',
    'Lutomiersk': 'PL-LD', 'Duszniki-Zdrój': 'PL-DS', 'Grodzisk Mazowiecki': 'PL-MZ', 'Świebodzice': 'PL-DS',
    'Sieradz': 'PL-LD', 'Kamieniec Wrocławski': 'PL-DS', 'Jedlińsk': 'PL-MZ', 'Stryków': 'PL-LD',
    'Brzeszcze': 'PL-MA', 'Skawina': 'PL-MA', 'Zgorzelec': 'PL-DS', 'Dąbrowa Tarnowska': 'PL-MA',
    'Bezrzecze': 'PL-ZP', 'Mińsk Mazowiecki': 'PL-MZ', 'Janikowo': 'PL-KP', 'Słupno': 'PL-MZ',
    'Limanowa': 'PL-MA', 'Ołtarzew': 'PL-MZ', 'Aleksandrów Kujawski': 'PL-KP', 'Pleszew': 'PL-WP',
    'Skórzewo': 'PL-WP', 'Koluszki': 'PL-LD', 'Lębork': 'PL-PM', 'Falenty': 'PL-MZ',
    'Białka Tatrzańska': 'PL-MA', 'Libertów': 'PL-MA', 'Borkowo Kościelne': 'PL-MZ', 'Lubartów': 'PL-LU',
    'Leżajsk': 'PL-PK', 'Choszczno': 'PL-ZP', 'Mysłakowice': 'PL-DS', 'Skuły': 'PL-MZ',
    'Kościelna Wieś': 'PL-WP', 'Wysokie Mazowieckie': 'PL-PD', 'Przystajń': 'PL-SL', 'Kolbudy': 'PL-PM',
    'Wadowice': 'PL-MA', 'Kęty': 'PL-MA', 'Czerwionka-Leszczyny': 'PL-SL', 'Maków Nowy': 'PL-MZ',
    'Nowiny': 'PL-SK', 'Jarkowice': 'PL-DS', 'Dobrzejewice': 'PL-KP', 'Bądkowo': 'PL-KP',
    'Wsola': 'PL-MZ', 'Kłodzko': 'PL-DS', 'Baranowo': 'PL-WP', 'Gąbin': 'PL-MZ',
    'Koniecpol': 'PL-SL', 'Ropczyce': 'PL-PK', 'Wojnicz': 'PL-MA', 'Jurgów': 'PL-MA',
    'Opole Lubelskie': 'PL-LU', 'Nowy Dwór Mazowiecki': 'PL-MZ', 'Ustroń': 'PL-SL', 'Wieliczka': 'PL-MA',
    'Gnojnik': 'PL-MA', 'Węgrzce Wielkie': 'PL-MA', 'Tyniec Mały': 'PL-DS', 'Głubczyce': 'PL-OP',
    'Golub-Dobrzyń': 'PL-KP', 'Gryfino': 'PL-ZP', 'Wieluń': 'PL-LD', 'Kowary': 'PL-DS',
    'Radziechowy': 'PL-SL', 'Konstantynów Łódzki': 'PL-LD', 'Słotwina': 'PL-SL', 'Zielonka': 'PL-MZ',
    'Kobiór': 'PL-SL', 'Strzelce Opolskie': 'PL-OP', 'Jawor': 'PL-DS', 'Stare Babice': 'PL-MZ',
    'Piotrków Kujawski': 'PL-KP', 'Przeźmierowo': 'PL-WP', 'Zieleniewo': 'PL-ZP', 'Radwanice': 'PL-DS',
    'Falenty Nowe': 'PL-MZ', 'Baryczka': 'PL-PK',
    'Bierwiecka Wola': 'PL-MZ', 'Bieniewice': 'PL-MZ', 'Raciąż': 'PL-MZ', 'Postomino': 'PL-ZP',
    'Ścinawa': 'PL-DS', 'Myślenice': 'PL-MA', 'Żernica': 'PL-SL', 'Paszkówka': 'PL-MA',
    'Stara Iwiczna': 'PL-MZ', 'Podlesie': 'PL-SL', 'Kalwaria Zebrzydowska': 'PL-MA',
    'Miejsce Piastowe': 'PL-PK', 'Kamyk': 'PL-SL',
    'Babiak': 'PL-WP', 'Klus': 'PL-WN', 'Przytyk': 'PL-MZ', 'Wilkowice': 'PL-SL',
    'Ludwinów': 'PL-MZ', 'Gdów': 'PL-MA', 'Żory': 'PL-SL', 'Ostrołęka': 'PL-MZ',
    'Jędrzejów': 'PL-SK', 'Nowodworce': 'PL-PD', 'Niechanowo': 'PL-WP',
    'Starowa Góra': 'PL-LD', 'Głogoczów': 'PL-MA', 'Buczkowice': 'PL-SL',
    'Krosno Odrzańskie': 'PL-LB', 'Żyrardów': 'PL-MZ', 'Kopanica': 'PL-WP',
    'Krotoszyn': 'PL-WP', 'Mory': 'PL-MZ', 'Piasek': 'PL-SL'
}

REGION_NAMES = {
    'PL-DS': 'Dolnośląskie',
    'PL-KP': 'Kujawsko-pomorskie',
    'PL-LU': 'Lubelskie',
    'PL-LB': 'Lubuskie',
    'PL-LD': 'Łódzkie',
    'PL-MA': 'Małopolskie',
    'PL-MZ': 'Mazowieckie',
    'PL-OP': 'Opolskie',
    'PL-PK': 'Podkarpackie',
    'PL-PD': 'Podlaskie',
    'PL-PM': 'Pomorskie',
    'PL-SL': 'Śląskie',
    'PL-SK': 'Świętokrzyskie',
    'PL-WN': 'Warmińsko-mazurskie',
    'PL-WP': 'Wielkopolskie',
    'PL-ZP': 'Zachodniopomorskie'
}

REGION_NAME_TO_CODE = {
    'dolnośląskie': 'PL-DS',
    'kujawsko-pomorskie': 'PL-KP',
    'lubelskie': 'PL-LU',
    'lubuskie': 'PL-LB',
    'łódzkie': 'PL-LD',
    'małopolskie': 'PL-MA',
    'mazowieckie': 'PL-MZ',
    'opolskie': 'PL-OP',
    'podkarpackie': 'PL-PK',
    'podlaskie': 'PL-PD',
    'pomorskie': 'PL-PM',
    'śląskie': 'PL-SL',
    'świętokrzyskie': 'PL-SK',
    'warmińsko-mazurskie': 'PL-WN',
    'wielkopolskie': 'PL-WP',
    'zachodniopomorskie': 'PL-ZP'
}


def resolve_region(region, city=None):
    """Return a known voivodeship code (a key of REGION_NAMES) or None.

    Accepts a code or a Polish region name, else falls back to the city: the voivodeship named
    after its comma (autoplac and OLX store 'Tarnów, Małopolskie'), then the region of a known
    place. Anything else (e.g. a stray 5-char string) is dropped so maps never get unknown keys.
    """
    if region:
        region = region.strip()
        if region in REGION_NAMES:
            return region
        code = REGION_NAME_TO_CODE.get(region.lower())
        if code:
            return code
    if not city:
        return None
    parts = city.split(",")
    if len(parts) > 1:
        code = REGION_NAME_TO_CODE.get(parts[-1].strip().lower())
        if code:
            return code
    place = place_name(city)
    code = CITY_TO_REGION.get(place)
    if code in REGION_NAMES:
        return code
    return "PL-WP" if place in WIELKOPOLSKA_PLACES else None


def location(city, region=None):
    """{'place': 'Tarnów', 'region': 'PL-MA', 'region_name': 'Małopolskie'} for display: every page
    shows a listing's location this way, whatever format its site stored it in."""
    code = resolve_region(region, city)
    return {"place": place_name(city) or None, "region": code, "region_name": REGION_NAMES.get(code, "")}


# ── Distance from Poznań ────────────────────────────────────────────────────
# Listings carry a place name only, so the deals page (/deals) measures distance with this table
# of approximate coordinates (lat, lon) of places around Poznań and in the rest of Wielkopolska.
# A place missing here has an unknown distance; it shows up only when the whole voivodeship is
# chosen. Names that several villages share (Piotrowice, Kościelna Wieś, Lipka) are left out on
# purpose: a wrong guess would put a car 150 km away into "near Poznań".
POZNAN = (52.4064, 16.9252)

PLACE_COORDS = {
    # Poznań and the Poznań county
    'Poznań': (52.4064, 16.9252), 'Luboń': (52.347, 16.879), 'Puszczykowo': (52.284, 16.855),
    'Mosina': (52.245, 16.847), 'Swarzędz': (52.411, 17.073), 'Gruszczyn': (52.430, 17.060),
    'Zalasewo': (52.392, 17.090), 'Kamionki': (52.317, 17.005), 'Borówiec': (52.316, 16.990),
    'Kórnik': (52.247, 17.087), 'Tarnowo Podgórne': (52.466, 16.670), 'Przeźmierowo': (52.428, 16.790),
    'Baranowo': (52.437, 16.775), 'Swadzim': (52.458, 16.745), 'Wysogotowo': (52.414, 16.792),
    'Skórzewo': (52.397, 16.803), 'Dopiewo': (52.360, 16.700), 'Komorniki': (52.335, 16.810),
    'Golęczewo': (52.522, 16.918), 'Suchy Las': (52.470, 16.880), 'Owińska': (52.513, 16.997),
    'Czerwonak': (52.465, 16.985), 'Murowana Goślina': (52.574, 17.012), 'Rokietnica': (52.513, 16.746),
    'Cerekwica': (52.535, 16.693), 'Kostrzyn': (52.398, 17.229), 'Pobiedziska': (52.477, 17.290),
    'Kleszczewo': (52.338, 17.172), 'Stęszew': (52.283, 16.699), 'Buk': (52.355, 16.519),
    # Neighbouring counties
    'Grzebienisko': (52.452, 16.470), 'Szamotuły': (52.611, 16.580), 'Oborniki': (52.648, 16.810),
    'Śrem': (52.089, 17.015), 'Środa Wielkopolska': (52.228, 17.278), 'Września': (52.325, 17.566),
    'Gniezno': (52.535, 17.583), 'Skiereszewo': (52.560, 17.540), 'Grodzisk Wielkopolski': (52.227, 16.366),
    'Opalenica': (52.309, 16.413), 'Nowy Tomyśl': (52.318, 16.128), 'Pniewy': (52.509, 16.255),
    'Kościan': (52.087, 16.645), 'Krzywiń': (51.966, 16.817), 'Bielewo': (51.990, 16.790),
    'Wolsztyn': (52.116, 16.115), 'Przemęt': (51.990, 16.300), 'Wągrowiec': (52.808, 17.199),
    'Międzychód': (52.600, 15.890), 'Słupca': (52.287, 17.872), 'Pyzdry': (52.170, 17.690),
    'Jarocin': (51.973, 17.502), 'Gostyń': (51.880, 17.012), 'Leszno': (51.840, 16.575),
    'Czarnków': (52.902, 16.563), 'Chodzież': (52.995, 16.919),
    # The rest of Wielkopolska and the nearest cities beyond it
    'Krobia': (51.774, 16.983), 'Szamocin': (53.030, 17.130), 'Ujście': (53.053, 16.733),
    'Piła': (53.151, 16.738), 'Trzcianka': (53.041, 16.455), 'Złotów': (53.363, 17.040),
    'Konin': (52.223, 18.251), 'Koło': (52.200, 18.638), 'Turek': (52.015, 18.500),
    'Pleszew': (51.896, 17.786), 'Krotoszyn': (51.697, 17.437), 'Ostrów Wielkopolski': (51.655, 17.807),
    'Przygodzice': (51.600, 17.810), 'Kalisz': (51.762, 18.091), 'Kępno': (51.278, 17.989),
    'Gorzów Wielkopolski': (52.731, 15.240), 'Zielona Góra': (51.935, 15.506),
    'Bydgoszcz': (53.123, 18.008), 'Inowrocław': (52.798, 18.261), 'Wrocław': (51.108, 17.039),
}
WIELKOPOLSKA_PLACES = frozenset(PLACE_COORDS) - {
    'Gorzów Wielkopolski', 'Zielona Góra', 'Bydgoszcz', 'Inowrocław', 'Wrocław'}


def place_name(city):
    """The bare place name of a listing's location: 'Poznań, Wielkopolskie' and
    'Poznań - Grunwald' become 'Poznań'."""
    return (city or "").split(",")[0].split(" - ")[0].strip()


def km_from_poznan(city):
    """Straight-line distance in km from the centre of Poznań, or None for an unknown place."""
    coords = PLACE_COORDS.get(place_name(city))
    if not coords:
        return None
    lat1, lon1 = map(math.radians, POZNAN)
    lat2, lon2 = map(math.radians, coords)
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return round(2 * 6371 * math.asin(math.sqrt(a)))
