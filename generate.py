import os
import shutil
from datetime import datetime
import markdown
from jinja2 import Environment, FileSystemLoader
import re
import jdatetime

# --- Configuration ---
CONTENT_PATH = 'content'
TEMPLATE_PATH = 'templates'
OUTPUT_PATH = 'output'
STATIC_PATH = 'static'
RESOURCES_PATH = 'content/resources'
RESOURCES_OUT = 'resources'

# --- Helper Functions ---

def display_status_filter(status):
    """A Jinja2 filter to convert status slugs to readable Persian text."""
    status_map = {
        'held': 'برگزار شده',
        'upcoming': 'در پیش رو',
        'cancelled': 'لغو شده'
    }
    return status_map.get(status, status)

def to_jalali_filter(gregorian_date):
    """A Jinja2 filter to convert Gregorian datetime object to a Jalali date string."""
    j_months = [
        "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
        "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
    ]
    try:
        datetime_object = datetime.fromisoformat(gregorian_date)
        jalali_date = jdatetime.date.fromgregorian(date=datetime_object)
        day = jalali_date.day
        month_name = j_months[jalali_date.month - 1]
        year = jalali_date.year
        return f"{day} {month_name} {year}"
    except Exception as e:
        return gregorian_date

def clean_and_create_output_dir():
    """Removes the old output directory and creates a new one."""
    if os.path.exists(OUTPUT_PATH):
        shutil.rmtree(OUTPUT_PATH)
    os.makedirs(OUTPUT_PATH)
    print("✅ Output directory created.")

def copy_static_files():
    """Copies static files (CSS, images) to the output directory."""
    static_output_path = os.path.join(OUTPUT_PATH, 'static')
    if os.path.exists(STATIC_PATH):
        shutil.copytree(STATIC_PATH, static_output_path)
        print("✅ Static files copied.")

def copy_resource_files():
    """Copies resource files (images, etc) to the output directory."""
    static_output_path = os.path.join(OUTPUT_PATH, 'resources')
    if os.path.exists(RESOURCES_PATH):
        shutil.copytree(RESOURCES_PATH, static_output_path)
        print("✅ Resource files copied.")

def load_content(content_type):
    """Loads and parses all markdown files from a specific content directory."""
    items = []
    path = os.path.join(CONTENT_PATH, content_type)
    if not os.path.isdir(path):
        return []

    md = markdown.Markdown(extensions=['meta'])
    for filename in os.listdir(path):
        if filename.endswith('.md'):
            filepath = os.path.join(path, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
                text = re.sub(
                    r'!\[(.*?)\]\((?!https?://|/)(.*?)\)',
                    rf'![\1](/{RESOURCES_OUT}/\2)',
                    text
                )
                text = re.sub(
                    r'<img(.*?)src="(?!https?://|/)(.*?)"',
                    r'<img\1src="/resources/\2"',
                    text
                )
                html = md.convert(text)
                meta = {k: v[0] if len(v) == 1 else v for k, v in md.Meta.items()}
                item = {
                    'html': html,
                    'slug': os.path.splitext(filename)[0],
                    **meta
                }
                if content_type in ['events', 'news'] and 'date' in item:
                    try:
                        item['date_obj'] = datetime.strptime(item['date'], '%Y-%m-%d')
                    except ValueError:
                        print(f"⚠️ Warning: Invalid date format in {filename}. Use YYYY-MM-DD.")
                        item['date_obj'] = datetime.now()
                items.append(item)

    if content_type in ['events', 'news']:
        items.sort(key=lambda x: x.get('date_obj', datetime.min), reverse=True)

    print(f"📚 Loaded {len(items)} items from '{content_type}'.")
    return items

def find_main_page_event(events):
    """Finds the next upcoming event, or the last held one."""
    now = datetime.now()
    upcoming_events = [e for e in events if e.get('status') == 'upcoming' and e.get('date_obj') > now]
    if upcoming_events:
        return min(upcoming_events, key=lambda x: x['date_obj'])
    elif events:
        return events[0]
    return None

def get_full_url(base_url, path):
    """Constructs a full URL from a base and a path."""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

def render_site(env, data):
    """Renders all HTML pages with OG data."""
    people_map = {p['slug']: p for p in data['people']}
    base_url = data['site_config']['base_url']

    # --- 1. Render Main Pages (Index, About, etc.) ---
    main_event = find_main_page_event(data['events'])
    index_og_data = {
        'title': data['site_config']['title'],
        'description': data['site_config']['description'],
        'url': base_url,
        'image': get_full_url(base_url, data['site_config']['og_image']),
        'type': 'website'
    }
    template = env.get_template('index.html')
    with open(os.path.join(OUTPUT_PATH, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(template.render(main_event=main_event, site=data, og_data=index_og_data))

    template = env.get_template('page_detail.html')
    for page in data['pages']:
        page_url = get_full_url(base_url, f"{page['slug']}.html")
        page_og_image = get_full_url(base_url, page.get('image', data['site_config']['og_image']))
        page_og_data = {
            'title': f"{page.get('title', 'صفحه')} | {data['site_config']['title']}",
            'description': page.get('summary', data['site_config']['description']),
            'url': page_url,
            'image': page_og_image,
            'type': 'website'
        }
        with open(os.path.join(OUTPUT_PATH, f"{page['slug']}.html"), 'w', encoding='utf-8') as f:
            f.write(template.render(page=page, site=data, og_data=page_og_data))

    # --- 2. Render List Pages ---
    list_template = env.get_template('list_page.html')
    content_type_persian = {
        'events': 'رویدادها',
        'people': 'افراد',
        'projects': 'پروژه‌ها',
        'news': 'اخبار'
    }
    for content_type, items in data.items():
        if content_type in ['events', 'people', 'projects', 'news']:
            output_dir = os.path.join(OUTPUT_PATH, content_type)
            os.makedirs(output_dir, exist_ok=True)
            with open(os.path.join(output_dir, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(list_template.render(
                    items=items,
                    title=f"فهرست {content_type_persian[content_type]}",
                    content_type=content_type,
                    site=data
                ))

    # --- 3. Render Detail Pages ---
    detail_templates = {
        'events': env.get_template('event_detail.html'),
        'people': env.get_template('person_detail.html'),
        'projects': env.get_template('project_detail.html'),
        'news': env.get_template('news_detail.html')
    }
    for content_type, items in data.items():
        if content_type in detail_templates:
            template = detail_templates[content_type]
            for item in items:
                item_og_image = get_full_url(base_url, item.get('image', data['site_config']['og_image']))
                if content_type == 'events' and 'presenters' in item:
                    presenter_slugs = item['presenters'] if isinstance(item['presenters'], list) else [item['presenters']]
                    item['presenter_details'] = [people_map.get(p_slug) for p_slug in presenter_slugs if p_slug in people_map and people_map.get(p_slug) is not None]
                item_url = get_full_url(base_url, f"{content_type}/{item['slug']}.html")
                item_og_data = {
                    'title': f"{item.get('title', 'مورد')} | {data['site_config']['title']}",
                    'description': item.get('summary', data['site_config']['description']),
                    'url': item_url,
                    'image': item_og_image,
                    'type': 'article'
                }
                os.makedirs(os.path.join(OUTPUT_PATH, content_type), exist_ok=True)
                with open(os.path.join(OUTPUT_PATH, content_type, f"{item['slug']}.html"), 'w', encoding='utf-8') as f:
                    f.write(template.render(item=item, site=data, og_data=item_og_data))

    print("✅ All pages rendered successfully.")

def main():
    """Main function to generate the entire site."""
    print("🚀 Starting ZanjanLUG site generation...")
    clean_and_create_output_dir()
    env = Environment(loader=FileSystemLoader(TEMPLATE_PATH))
    env.filters['jalali'] = to_jalali_filter
    env.filters['display_status'] = display_status_filter

    data = {
        'events': load_content('events'),
        'people': load_content('people'),
        'projects': load_content('projects'),
        'pages': load_content('pages'),
        'news': load_content('news'),
        'site_config': {
            'title': "زنجان‌لاگ",
            'base_url': 'https://zanjanlug.ir',
            'description': 'گروه کاربران لینوکس زنجان (زنجان‌لاگ)، جامعه‌ای برای علاقه‌مندان به نرم‌افزار آزاد و متن‌باز در زنجان.',
            'og_image': '/static/images/zanjanlug_logo_square.png'
        },
        'social_links': [
            {'name': 'تلگرام', 'url': 'https://t.me/zanjan_lug'},
            {'name': 'ماستودون', 'url': 'https://ohai.social/@zanjanlug'},
            {'name': 'وبسایت', 'url': 'https://zanjanlug.ir'},
        ]
    }

    render_site(env, data)
    copy_static_files()
    copy_resource_files()
    print("🎉 Site generation complete! Check the 'output' directory.")

if __name__ == '__main__':
    main()
