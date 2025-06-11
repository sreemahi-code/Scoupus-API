import requests
import sqlite3

# Constants
API_KEY = '25ff00d77368e3b4364acb9bc0dbc449'  # Replace with your actual Elsevier API key
SCOPUS_ID = '55734229300'  # Replace with your actual Scopus ID
HEADERS = {
    'X-ELS-APIKey': API_KEY,
    'Accept': 'application/json'
}

# Step 1: Fetch data from Scopus Abstract API
def fetch_document(scopus_id):
    url = f'https://api.elsevier.com/content/abstract/scopus_id/{scopus_id}'
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch data: {response.status_code} - {response.text}")

    return response.json()

# Step 2: Extract relevant fields
def parse_document(data):
    doc = data['abstracts-retrieval-response']

    title = doc.get('coredata', {}).get('dc:title', '')
    abstract = doc.get('coredata', {}).get('dc:description', '')
    document_type = doc.get('coredata', {}).get('subtypeDescription', '')
    source_type = doc.get('coredata', {}).get('prism:aggregationType', '')
    journal = doc.get('coredata', {}).get('prism:publicationName', '')
    doi = doc.get('coredata', {}).get('prism:doi', '')
    pub_date = doc.get('coredata', {}).get('prism:coverDate', '')
    citation_count = doc.get('coredata', {}).get('citedby-count', 0)

    authors = doc.get('authors', {}).get('author', [])
    author_list = [f"{a.get('ce:given-name', '')} {a.get('ce:surname', '')}" for a in authors]
    first_author = author_list[0] if author_list else ''
    corresponding_author = ''
    for a in authors:
        if a.get('@correspondence') == 'yes':
            corresponding_author = f"{a.get('ce:given-name', '')} {a.get('ce:surname', '')}"
            break

    return {
        'scopus_id': SCOPUS_ID,
        'title': title,
        'abstract': abstract,
        'document_type': document_type,
        'source_type': source_type,
        'journal': journal,
        'doi': doi,
        'pub_date': pub_date,
        'citation_count': citation_count,
        'author_list': "; ".join(author_list),
        'first_author': first_author,
        'corresponding_author': corresponding_author
    }

# Step 3: Save to SQLite database
def save_to_db(doc_info):
    conn = sqlite3.connect('scopus_documents.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            scopus_id TEXT PRIMARY KEY,
            title TEXT,
            abstract TEXT,
            document_type TEXT,
            source_type TEXT,
            journal TEXT,
            doi TEXT,
            pub_date TEXT,
            citation_count INTEGER,
            author_list TEXT,
            first_author TEXT,
            corresponding_author TEXT
        )
    ''')

    cursor.execute('''
        INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        doc_info['scopus_id'],
        doc_info['title'],
        doc_info['abstract'],
        doc_info['document_type'],
        doc_info['source_type'],
        doc_info['journal'],
        doc_info['doi'],
        doc_info['pub_date'],
        doc_info['citation_count'],
        doc_info['author_list'],
        doc_info['first_author'],
        doc_info['corresponding_author']
    ))

    conn.commit()
    conn.close()
    print(f"✅ Document {doc_info['scopus_id']} saved to database.")

# Run the script
if __name__ == '__main__':
    try:
        raw_data = fetch_document(SCOPUS_ID)
        parsed_doc = parse_document(raw_data)
        save_to_db(parsed_doc)
    except Exception as e:
        print(f"❌ Error: {e}")

