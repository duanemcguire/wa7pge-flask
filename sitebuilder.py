import re
import sys
import os
import sqlite3
import re
from flask import Flask, request, render_template, abort, url_for, make_response
from flask_flatpages import FlatPages
from flask_frozen import Freezer
from datetime import datetime
from pathlib import Path


DEBUG = True
FLATPAGES_AUTO_RELOAD = DEBUG
FLATPAGES_EXTENSION = '.md'
app = Flask(__name__)
app.config.from_object(__name__)
pages = FlatPages(app)
park_db_path = os.path.expanduser("~/docs/projects/Ham Radio/POTA/usa.db")


# check data
err = False
for p in pages:
    if type(p.meta['date']) is not str:
        err = True 
        print (f"Bad date string: {p.path} {type(p.meta['date'])}")
    if 'title' not in p.meta:
        err = True 
        print (f"No Title: {p.path} {type(p.meta['date'])}")
    else:
        if type(p.meta['title']) is not str:
            err = True 
            print (f"Title is not string: {p.path} {type(p.meta['date'])}")
if err:
    raise ValueError("Bad Markdown")            

freezer = Freezer(app)


def remove_html_tags(str):
    return re.compile(r'<[^>]+>').sub('', str)


def reverse(s):
    str = ""
    for i in s:
        str = i + str
    return str


def get_excerpt(html, n):
    txt = remove_html_tags(html)
    txt = reverse(txt.strip()[:n])
    i = txt.find(' ')
    txt = txt[i+1:]
    txt = reverse(txt)
    return txt


def get_thumb_from_photoset(photoset):
    for photo in photoset:
        if 'thumbnail' in photo and photo['thumbnail'] == 'True':
            img = photo['path'].replace('/images', '/images/thumb')
            return img
    return ""


def add_extra_meta(p):
    if 'excrpt' not in p.meta:
        p.meta['excrpt'] = get_excerpt(p.html, 100)
    if 'img' not in p.meta :
        p.meta['img'] = get_last_image_url(p.body)
    # set pub_date for rss.xml
    d = datetime.strptime(p.meta['date'][:10],'%Y-%m-%d')
    p.meta['pub_date'] = datetime.strftime(d, '%a, %d %b %Y 00:00:00 GMT')    
    # Set image for pagefind
    p.html = p.html.replace("<img",'<img data-pagefind-meta="image[src]" ',1 )    

    return p


def add_cat_html(p):
    if 'category' in p.meta:
        c = ""
        cat_html = ""
        for cat in p.meta['category']:
            cat_html = cat_html + \
                f'{c} <a href="/category/{cat}/">{CATEGORY_DICT[cat]}</a>'
            c = ','
        p.meta['cat_html'] = cat_html
        p.meta['hyvor_id'] = p.path.split('/')[-1]
    return p


def get_last_image_url(content):
    # Regex to capture image URLs: ![alt text](url)
    urls = re.findall(r'!\[[^\]]*\]\((.*?)\)', content)
    # Return the last URL if any found
    return urls[-1] if urls else None

def catpic(cat):
    
    posts = (p for p in pages
        if p.path.split('/')[0] == cat
        and 'date' in p.meta
        )
    p2 = []
    for p in posts:
        p = add_extra_meta(p)
        p2.append(p)
    latest = sorted(p2, reverse=True,
                    key=lambda p: p.meta['date'])
    return latest

#            + f"><a href='{link}'</a>{bc}"  


def breadcrumbs(path):
    # remove leading and trailing "/" from path   
    path = path[1:][:-1]
    
    html = "<a href='/'>Home</a>"
    link = ""
    bc_elements = path.split("/")
    for bc in bc_elements:
        link = link + f"/{bc}"
        html = html + "><a href='" + link + "'>" + bc + "</a>"
    return html

def find_first_file_starting_with(root_path, prefix):
    root = Path(root_path)
    for p in root.rglob(f"{prefix}*"):
        if p.is_file():
            return p
    return None

def lookup_park(filename):
    """
    Updates the title of a photo in Shotwell's database.
    """
    #If the filename shows what park it is, get the URL directly. 
    filename  = os.path.basename(filename)
    pattern = r"US-\d+\.\w+"
    ret = "#"
    m = re.match(pattern,filename)
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    os.chdir(current_dir)

    start_with = f"{current_dir}/pages/POTA/"
    replacement = "/POTA/"

    if m:
        path = find_first_file_starting_with(start_with, m.group(0).split('.')[0])
        try:
            path = str(path)
            path = path.replace(start_with,replacement)
            path = path.replace(".md","", 1)
        except TypeError:
            path = "#"
        except AttributeError:
            path = "#"            
        ret = path
    else:
        try:
            path = str(find_park(filename))
            print(path)
            print(start_with)
            path = path.replace(start_with,replacement)
            path = path.replace(".md","", 1)
        except TypeError:
            print(f"typeError: {path}")
            path = "#"
        except AttributeError:
            path = "#"            
    ret = path
    return ret    

def find_park(search_text, directory="/home/duane/Dropbox/Docs/code/wa7pge-flask/pages/POTA"):
    """
    Search .md files in the given directory for a specific text string.

    :param directory: Directory path to search.
    :param search_text: Text string to search for.
    :return: List of filenames containing the search string.
    """
    matching_files = []
    for root, dirs, files in os.walk(directory):

        for file in files:
            if file.lower().endswith(".md"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if search_text in content:
                            matching_files.append(file_path)
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
    if len(matching_files):

        return matching_files[0]
    else:
        return ""





@app.route('/')
def index():
    # posts are pages with a publication date
    page=pages.get_or_404('Main/index')
    page = add_extra_meta(page)
    # Get the most recent posts

    posts = (p for p in pages
            if 'date' in p.meta
            )


    latest = sorted(posts, reverse=True,
                    key=lambda p: p.meta['date'])[:7]

    return render_template('home/home.html',
                           latest=latest,                            
                           h2="Home",page=page,
                           breadcrumbs=breadcrumbs(request.path)
                           )
@app.route('/Equipment/')
def equpipment():
    return render_template('tiles.html', 
                           posts=catpic("Equipment"),
                           h2="Equipment",
                           breadcrumbs=breadcrumbs(request.path)
                           )

@app.route('/Antennas/')
def antennas():
    return render_template('tiles.html', 
                           posts=catpic("Antennas"),
                           h2="Antennas",
                           breadcrumbs=breadcrumbs(request.path))

@app.route('/Thoughts/')
def thoughts():
    return render_template('tiles.html', 
                           posts=catpic("Thoughts"),
                           h2="Thoughts",
                           breadcrumbs=breadcrumbs(request.path))







@app.route('/CW/')
def CW():
    posts = (p for p in pages
        if p.path.split('/')[0] == "CW"
        and p.path.split('/')[1] != 'index'
        and 'date' in p.meta
        )
    latest = sorted(posts, reverse=True,
                    key=lambda p: p.meta['date'])
    post_index = (p for p in pages
        if p.path.split('/')[0] == "CW"
        and p.path.split('/')[1] == 'index'
        )
    try:
        post_index = next(iter(post_index))
    except StopIteration:
        post_index = None
    return render_template('CW.html', posts=latest,
                           post_index=post_index,
                           breadcrumbs=breadcrumbs(request.path)
                           )


@app.route('/POTA/')
def pota():
    page=pages.get_or_404('POTA/index')
    page = add_extra_meta(page)
    return render_template('page.html',
                           h2="POTA",page=page, breadcrumbs=breadcrumbs(request.path))

@app.route('/POTA/Hunted/')
def potastates():
    states = []
    state_counts = dict()
    for p in pages:
        if p.path.split('/')[1] == "Hunted":
            spc = p.path.split('/')[2]
            if spc not in states:
                states.append(spc)
                state_counts.update({spc: 1})
            else:
                state_counts[spc] = state_counts[spc] +1
    states.sort()                
    return render_template('pota-states.html', 
                           breadcrumbs=breadcrumbs(request.path),
                           states=states, 
                           state_counts=state_counts,
                           noindex=True  )    



@app.route('/POTA/Hunted/<spc>/')
def potahunt(spc):

    posts = (p for p in pages
        if p.path.split('/')[-2] == spc
        )
    p2 = []
    for p in posts:
        p = add_extra_meta(p)
        p2.append(p)
        
    return render_template('tiles.html', posts=p2,
                           h2=f"{spc} Parks Hunted",
                           breadcrumbs=breadcrumbs(request.path),
                           noindex=True)    



@app.route('/POTA/Activations/')

def potaactivated():
    activations = []
    posts = (p for p in pages
        if p.path.split('/')[1] == "Activations"      
        )
    for p in posts:
        activations.append({'state': p.meta['spc'], 'post': p})
    activations = sorted(activations, key=lambda x: x['state'])
    
    return render_template('pota-activations.html', activations=activations, breadcrumbs=breadcrumbs(request.path),noindex=True) 



@app.route('/<path:path>')
@app.route('/<path:path>/')
def page(path):
    page = pages.get_or_404(path)
    return render_template('page.html', page=page, breadcrumbs=breadcrumbs(request.path) )


@app.route('/Search/')
def search():
    return render_template('search.html', breadcrumbs=breadcrumbs(request.path))


@app.route('/POTA/Scenes/')
def pota_scenes():
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    os.chdir(current_dir)
    img_folder = "static/POTA-Scenes"
    images1 = sorted([f for f in os.listdir(img_folder)])
    images = []
    for image in images1:
        image = f"/{img_folder}/{image}"
        park_path = lookup_park(image)
        images.append([image,park_path])
 

    return render_template('pota-scenes.html', breadcrumbs=breadcrumbs(request.path), images=images)




@app.route('/rss.xml')
def rss():
    # posts are pages with a publication date
    posts = (p for p in pages if 'date' in p.meta)
    latest = sorted(posts, reverse=True,
                    key=lambda p: p.meta['date'])
    latest_rev = []
    for p in latest:
        p = add_extra_meta(p)
        latest_rev.append(p)
    rss_xml = render_template('rss.xml', posts=latest_rev,
        last_build_date=datetime.strftime(datetime.now(), '%a, %d %b %Y 00:00:00 GMT'))
    response = make_response(rss_xml)
    response.headers['Content-Type'] = 'application/rss+xml'
    return response


@freezer.register_generator
def pagelist():
    for page in pages:
        yield url_for('page', path=page.path)
        pathsplit = page.path.split("/")
        if pathsplit[1] == "Hunted":
            yield url_for('potahunt', spc=pathsplit[2])                



if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'build':
        freezer.freeze()
    else:
        app.run(host='0.0.0.0', port=5002)
