from django.core.management.base import BaseCommand
from orders.models import ClothingItem, Valet


# The catalog of items Rinse supports.
# Each dict maps directly to ClothingItem fields.
CLOTHING_ITEMS = [
    # Tops
    {'name': 'Dress Shirt',     'slug': 'dress-shirt',    'category': 'tops',      'price': '5.99',  'icon': '👔'},
    {'name': 'T-Shirt',         'slug': 't-shirt',         'category': 'tops',      'price': '3.99',  'icon': '👕'},
    {'name': 'Polo Shirt',      'slug': 'polo-shirt',      'category': 'tops',      'price': '4.99',  'icon': '👕'},
    {'name': 'Button-Down',     'slug': 'button-down',     'category': 'tops',      'price': '4.99',  'icon': '👔'},
    {'name': 'Tank Top',        'slug': 'tank-top',        'category': 'tops',      'price': '2.99',  'icon': '👕'},

    # Bottoms
    {'name': 'Pants',           'slug': 'pants',           'category': 'bottoms',   'price': '6.99',  'icon': '👖'},
    {'name': 'Jeans',           'slug': 'jeans',           'category': 'bottoms',   'price': '6.99',  'icon': '👖'},
    {'name': 'Shorts',          'slug': 'shorts',          'category': 'bottoms',   'price': '4.99',  'icon': '🩳'},
    {'name': 'Track Pants',     'slug': 'track-pants',     'category': 'bottoms',   'price': '4.99',  'icon': '👖'},
    {'name': 'Skirt',           'slug': 'skirt',           'category': 'bottoms',   'price': '5.99',  'icon': '👗'},
    {'name': 'Leggings',        'slug': 'leggings',        'category': 'bottoms',   'price': '3.99',  'icon': '👖'},

    # Outerwear
    {'name': 'Suit Jacket',     'slug': 'suit-jacket',     'category': 'outerwear', 'price': '12.99', 'icon': '🧥'},
    {'name': 'Blazer',          'slug': 'blazer',          'category': 'outerwear', 'price': '11.99', 'icon': '🧥'},
    {'name': 'Coat / Overcoat', 'slug': 'coat',            'category': 'outerwear', 'price': '14.99', 'icon': '🧥'},
    {'name': 'Puffer Jacket',   'slug': 'puffer-jacket',   'category': 'outerwear', 'price': '13.99', 'icon': '🧥'},
    {'name': 'Sweater / Hoodie','slug': 'sweater-hoodie',  'category': 'outerwear', 'price': '7.99',  'icon': '🧶'},

    # Formal
    {'name': 'Suit (2-piece)',  'slug': 'suit-2-piece',    'category': 'formal',    'price': '24.99', 'icon': '🤵'},
    {'name': 'Tuxedo',          'slug': 'tuxedo',          'category': 'formal',    'price': '29.99', 'icon': '🤵'},
    {'name': 'Dress',           'slug': 'dress',           'category': 'formal',    'price': '14.99', 'icon': '👗'},
    {'name': 'Saree / Ethnic',  'slug': 'saree-ethnic',    'category': 'formal',    'price': '19.99', 'icon': '🥻'},

    # Household
    {'name': 'Bedsheet',        'slug': 'bedsheet',        'category': 'household', 'price': '8.99',  'icon': '🛏️'},
    {'name': 'Duvet / Comforter','slug': 'duvet',          'category': 'household', 'price': '19.99', 'icon': '🛏️'},
    {'name': 'Towel',           'slug': 'towel',           'category': 'household', 'price': '4.99',  'icon': '🧺'},
]

# 5 simulated valets based in San Francisco
# Coordinates are spread across SF neighborhoods
VALETS = [
    {'name': 'Marcus Johnson', 'phone': '415-555-0101', 'latitude': 37.7749,  'longitude': -122.4194},  # Downtown
    {'name': 'Sofia Rivera',   'phone': '415-555-0102', 'latitude': 37.7849,  'longitude': -122.4094},  # North Beach
    {'name': 'James Chen',     'phone': '415-555-0103', 'latitude': 37.7649,  'longitude': -122.4294},  # Mission
    {'name': 'Aisha Patel',    'phone': '415-555-0104', 'latitude': 37.7949,  'longitude': -122.4394},  # Marina
    {'name': 'Derek Williams', 'phone': '415-555-0105', 'latitude': 37.7549,  'longitude': -122.4094},  # SoMa
]


class Command(BaseCommand):
    # This string shows up when you run: python manage.py help seed_items
    help = 'Seed the database with the ClothingItem catalog'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete all existing ClothingItems and Valets before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            ClothingItem.objects.all().delete()
            Valet.objects.all().delete()
            self.stdout.write(self.style.WARNING('Cleared all existing ClothingItems and Valets.'))

        # --- Seed ClothingItems ---
        items_created = 0
        items_skipped = 0
        for item_data in CLOTHING_ITEMS:
            obj, created = ClothingItem.objects.get_or_create(
                slug=item_data['slug'],
                defaults=item_data,
            )
            if created:
                items_created += 1
            else:
                items_skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'ClothingItems — Created: {items_created}, Skipped: {items_skipped}'
        ))

        # --- Seed Valets ---
        valets_created = 0
        valets_skipped = 0
        for valet_data in VALETS:
            obj, created = Valet.objects.get_or_create(
                name=valet_data['name'],
                defaults=valet_data,
            )
            if created:
                valets_created += 1
            else:
                valets_skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'Valets — Created: {valets_created}, Skipped: {valets_skipped}'
        ))
