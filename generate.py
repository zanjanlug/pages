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
    return status_map.get(status, status) # اگر وضعیت نبود، خودش را برگردان

def to_jalali_filter(gregorian_date):
    """A Jinja2 filter to convert Gregorian datetime object to a Jalali date string."""

    # لیست نام ماه‌های فارسی
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
        # در صورت بروز خطا، تاریخ میلادی را به عنوان جایگزین برگردان
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
        print("✅ Static files copied.")

def load_content(content_type):
    """Loads and parses all markdown files from a specific content directory."""
    items = []
    path = os.path.join(CONTENT_PATH, content_type)
    if not os.path.isdir(path):
        return []

    # Initialize markdown with meta extension
    md = markdown.Markdown(extensions=['meta'])

    for filename in os.listdir(path):
        if filename.endswith('.md'):
            filepath = os.path.join(path, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()

                # --- START OF MODIFICATION ---
                # Use regex to prepend /resources/ to relative image paths.
                # This handles both Markdown `![alt](image.jpg)` and HTML `<img src="image.jpg">`.
                # It avoids changing absolute URLs (http://, https://, /).
                
                # For Markdown links: ![...](...)
                text = re.sub(
                    r'!\[(.*?)\]\((?!https?://|/)(.*?)\)',
                    rf'![\1](/{RESOURCES_OUT}/\2)',
                    text
                )
                # For HTML links: <img src="..." >
                text = re.sub(
                    r'<img(.*?)src="(?!https?://|/)(.*?)"',
                    r'<img\1src="/resources/\2"',
                    text
                )
                # --- END OF MODIFICATION ---

                html = md.convert(text)

                # Clean up metadata
                meta = {k: v[0] if len(v) == 1 else v for k, v in md.Meta.items()}

                item = {
                    'html': html,
                    'slug': os.path.splitext(filename)[0],
                    **meta
                }

                # Convert date strings to datetime objects for events
                if content_type == 'events' and 'date' in item:
                    try:
                        item['date_obj'] = datetime.strptime(item['date'], '%Y-%m-%d')
                    except ValueError:
                        print(f"⚠️ Warning: Invalid date format in {filename}. Use YYYY-MM-DD.")
                        item['date_obj'] = datetime.now() # Fallback

                items.append(item)

    # Sort events by date (newest first)
    if content_type == 'events':
        items.sort(key=lambda x: x.get('date_obj', datetime.min), reverse=True)

    print(f"📚 Loaded {len(items)} items from '{content_type}'.")
    return items
def find_main_page_event(events):
    """Finds the next upcoming event, or the last held one."""
    now = datetime.now()
    upcoming_events = [e for e in events if e.get('status') == 'upcoming' and e.get('date_obj') > now]

    if upcoming_events:
        # Return the closest upcoming event
        return min(upcoming_events, key=lambda x: x['date_obj'])
    elif events:
        # Return the most recent past event
        return events[0]
    return None

def render_site(env, data):
    """Renders all HTML pages."""
    people_map = {p['slug']: p for p in data['people']}

    # --- 1. Render Main Pages (Index, About, etc.) ---
    # Index page
    main_event = find_main_page_event(data['events'])
    template = env.get_template('index.html')
    with open(os.path.join(OUTPUT_PATH, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(template.render(main_event=main_event, site=data))

    # Static pages (e.g., about)
    template = env.get_template('page_detail.html') # A generic template for pages
    for page in data['pages']:
        with open(os.path.join(OUTPUT_PATH, f"{page['slug']}.html"), 'w', encoding='utf-8') as f:
            f.write(template.render(page=page, site=data))

    # --- 2. Render List Pages (Events, People, Projects) ---
    list_template = env.get_template('list_page.html')
    content_type_persian = {
        'events': 'رویدادها',
        'people': 'افراد',
        'projects': 'پروژه‌ها',
    }
    for content_type, items in data.items():
        if content_type in ['events', 'people', 'projects']:
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
    # Event details

      
    # در تابع render_site

    # Event details
    event_template = env.get_template('event_detail.html')
    for event in data['events']:
        # --- START OF MODIFICATION ---
        # Link presenters' data to the event
        if 'presenters' in event:
            presenters_data = event['presenters']
            
            # مطمئن می‌شویم که همیشه یک لیست از اسلاگ‌ها داریم، حتی اگر فقط یک ارائه‌دهنده وجود داشته باشد
            if isinstance(presenters_data, str):
                presenter_slugs = [presenters_data]  # اگر رشته بود، آن را به لیست تک عضوی تبدیل کن
            else:
                presenter_slugs = presenters_data  # در غیر این صورت، همان لیست است

            # حالا با لیست یکپارچه شده، اطلاعات کامل را استخراج می‌کنیم
            event['presenter_details'] = [people_map.get(p_slug) for p_slug in presenter_slugs if p_slug in people_map and people_map.get(p_slug) is not None]
        # --- END OF MODIFICATION ---

        with open(os.path.join(OUTPUT_PATH, 'events', f"{event['slug']}.html"), 'w', encoding='utf-8') as f:
            f.write(event_template.render(item=event, site=data))
    # Person details
    person_template = env.get_template('person_detail.html')
    for person in data['people']:
        with open(os.path.join(OUTPUT_PATH, 'people', f"{person['slug']}.html"), 'w', encoding='utf-8') as f:
            f.write(person_template.render(item=person, site=data))

    # Project details
    project_template = env.get_template('project_detail.html')
    for project in data['projects']:
        with open(os.path.join(OUTPUT_PATH, 'projects', f"{project['slug']}.html"), 'w', encoding='utf-8') as f:
            f.write(project_template.render(item=project, site=data))

    print("✅ All pages rendered successfully.")


# --- Main Execution ---
def main():
    """Main function to generate the entire site."""
    print("🚀 Starting ZanjanLUG site generation...")

    # 1. Setup environment
    clean_and_create_output_dir()
    env = Environment(loader=FileSystemLoader(TEMPLATE_PATH))
    env.filters['jalali'] = to_jalali_filter  # <--- این خط را اضافه کنید
    env.filters['display_status'] = display_status_filter  # <-- این خط را اضافه کنید

    # 2. Load all content
    # ... بقیه کد بدون تغییر ...    # 2. Load all content
    data = {
        'events': load_content('events'),
        'people': load_content('people'),
        'projects': load_content('projects'),
        'pages': load_content('pages'),
        # You can add global site variables here
        'site_title': "زنجان‌لاگ",
                # Add social media links
        'social_links': [
            {'name': 'تلگرام', 'url': 'https://t.me/zanjan_lug'},
            {'name': 'وبسایت', 'url': 'https://zanjanlug.ir'},
            # Add other links as needed
            # {'name': 'لینکدین', 'url': 'https://linkedin.com/yourusername'},
            # {'name': 'گیت‌هاب', 'url': 'https://github.com/yourusername'},
        ]
    }

    # 3. Render all pages
    render_site(env, data)

    # 4. Copy static files
    copy_static_files()
    copy_resource_files()

    print("🎉 Site generation complete! Check the 'output' directory.")

if __name__ == '__main__':
    main()
