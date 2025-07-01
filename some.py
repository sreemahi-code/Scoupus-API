import streamlit as st
import requests
import time
import pandas as pd

# Load API Key from Streamlit secrets
try:
    API_KEY = st.secrets["API_KEY"]
except KeyError:
    st.error("API_KEY not found in .streamlit/secrets.toml. Please add your Elsevier API key.")
    st.stop() # Stop the app if the key is not found

HEADERS = {
    'X-ELS-APIKey': API_KEY,
    'Accept': 'application/json'
}

# --- Function to get author's H-index ---
@st.cache_data(ttl=3600) # Cache results for 1 hour to avoid re-fetching on small UI changes
def get_author_h_index(scopus_id):
    """
    Fetches the h-index for a given Scopus author ID.
    """
    if not scopus_id:
        return 'N/A'
    h_index_url = f'https://api.elsevier.com/content/author/author_id/{scopus_id}?view=metrics'
    try:
        response = requests.get(h_index_url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        # Check if 'author-retrieval-response' exists and has elements
        if 'author-retrieval-response' in data and len(data['author-retrieval-response']) > 0:
            h_index = data['author-retrieval-response'][0].get('h-index', 'N/A')
        else:
            h_index = 'N/A' # Handle case where no author data is found
        return h_index
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching h-index for author {scopus_id}: {e}")
        return 'N/A'

# --- Search all documents by Scopus author ID (with pagination) ---
@st.cache_data(ttl=3600) # Cache results for 1 hour
def search_all_documents(scopus_id):
    """
    Searches for ALL documents by Scopus author ID, handling pagination.
    """
    if not scopus_id:
        return []

    all_entries = []
    search_url = 'https://api.elsevier.com/content/search/scopus'
    
    search_params = {
        'query': f'AU-ID({scopus_id})',
        'count': 25,  # Max count per page for Scopus API is usually 25 or 100
        'start': 0
    }
    
    progress_text = "Fetching documents..."
    my_bar = st.progress(0, text=progress_text)
    
    total_docs_fetched = 0
    total_results = 1 # Initialize to enter the loop

    while search_params['start'] < total_results:
        try:
            search_response = requests.get(search_url, headers=HEADERS, params=search_params)
            search_response.raise_for_status()
            search_data = search_response.json()
            
            entries = search_data.get('search-results', {}).get('entry', [])
            all_entries.extend(entries)

            total_results = int(search_data.get('search-results', {}).get('opensearch:totalResults', 0))
            items_per_page = int(search_data.get('search-results', {}).get('opensearch:itemsPerPage', 0))
            start_index = int(search_data.get('search-results', {}).get('opensearch:startIndex', 0))

            total_docs_fetched += len(entries)
            progress_percentage = min(total_docs_fetched / total_results, 1.0) if total_results > 0 else 1.0
            my_bar.progress(progress_percentage, text=f"{progress_text} ({total_docs_fetched}/{total_results} fetched)")

            if start_index + items_per_page < total_results:
                search_params['start'] += items_per_page
                time.sleep(1) # Respect rate limits before next page request
            else:
                break # No more pages
        except requests.exceptions.RequestException as e:
            st.error(f"Error during document search (page {search_params['start']}): {e}")
            break # Exit loop on error
    
    my_bar.empty() # Clear the progress bar when done
    return all_entries

# --- Get full abstract info for each document ---
@st.cache_data(ttl=3600) # Cache results for 1 hour
def get_abstract_details(eid):
    """
    Fetches abstract and author details for a given EID.
    """
    if not eid:
        return {}
    abstract_url = f'https://api.elsevier.com/content/abstract/eid/{eid}'
    
    try:
        abstract_response = requests.get(abstract_url, headers=HEADERS)
        abstract_response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        time.sleep(0.5) # Be mindful of rate limits
        return abstract_response.json().get('abstracts-retrieval-response', {})
    except requests.exceptions.RequestException as e:
        st.warning(f"Warning: Could not fetch abstract for EID {eid}. Error: {e}")
        return {}

# --- Streamlit UI ---
st.set_page_config(page_title="Scopus Author Data", layout="wide")

st.title(" Scopus Author Publication Data")
st.write("Enter a Scopus Author ID to retrieve their H-index and a list of their publications.")

scopus_id_input = st.text_input("Enter Scopus Author ID:", value="9736051900") # Default ID provided

if st.button("Fetch Data"):
    if not scopus_id_input:
        st.warning("Please enter a Scopus Author ID.")
    else:
        with st.spinner("Fetching author data... This might take a moment for many publications."):
            # Get H-index
            h_index = get_author_h_index(scopus_id_input)
            st.subheader(f"Author Metrics for ID: {scopus_id_input}")
            st.write(f"**H-index:** {h_index}")

            # Get all documents
            entries = search_all_documents(scopus_id_input)

            if not entries:
                st.warning("No documents found for this Scopus Author ID or an error occurred.")
                # Clear any previously selected document if no new documents are found
                if "selected_document_data" in st.session_state:
                    del st.session_state["selected_document_data"]
            else:
                st.subheader(f"Found {len(entries)} documents")
                
                # Prepare data for DataFrame
                documents_data_for_table = []
                # Store full document data, including abstract details, for later retrieval
                full_documents_data = {}

                abstract_progress_text = "Fetching abstracts and author details..."
                abstract_bar = st.progress(0, text=abstract_progress_text)

                for i, entry in enumerate(entries):
                    eid = entry.get('eid') or entry.get('full-abstract-retrieval', {}).get('eid')
                    title = entry.get('dc:title', 'N/A')
                    source = entry.get('prism:publicationName', 'N/A')
                    doi = entry.get('prism:doi', 'N/A')
                    date = entry.get('prism:coverDate', 'N/A')
                    cited_by = entry.get('citedby-count', '0')
                    doc_type = entry.get('subtypeDescription', 'N/A')
                    subtype = entry.get('subtype', 'N/A')

                    abstract_text = 'N/A'
                    all_authors = [] # Store as list of dicts for easier processing
                    author_names_str = 'N/A'
                    first_author = 'N/A'
                    corresponding_author = 'N/A'

                    if eid:
                        abstract_data = get_abstract_details(eid)
                        abstract_text = (
                            abstract_data.get('coredata', {}).get('dc:description') or
                            abstract_data.get('coredata', {}).get('description') or
                            'N/A'
                        )
                        
                        authors_raw = abstract_data.get('authors', {}).get('author', [])
                        all_authors = authors_raw # Keep raw for detailed display

                        author_names_list = [a.get('ce:indexed-name', 'N/A') for a in authors_raw]
                        author_names_str = ', '.join(author_names_list) if author_names_list else 'N/A'
                        first_author = author_names_list[0] if author_names_list else 'N/A'

                        for author in authors_raw:
                            if author.get('@corresponding', '').lower() == 'true':
                                corresponding_author = author.get('ce:indexed-name', 'N/A')
                                break
                    
                    # Data for the main table display (summary)
                    documents_data_for_table.append({
                        "Title": title,
                        "Journal Name": source,
                        "Published Date": date,
                        "Citations": int(cited_by), # Convert to int for sorting
                        "Document Type": doc_type,
                        "DOI": doi,
                        "EID": eid # Keep EID for lookup
                    })

                    # Store full details for specific document lookup
                    full_documents_data[eid] = {
                        "Title": title,
                        "Journal Name": source,
                        "Published Date": date,
                        "Citations": int(cited_by),
                        "Document Type": doc_type,
                        "Subtype": subtype,
                        "DOI": doi,
                        "EID": eid,
                        "Abstract": abstract_text,
                        "All Authors Raw": all_authors, # Store raw author data
                        "Authors List": author_names_list,
                        "First Author": first_author,
                        "Corresponding Author": corresponding_author
                    }
                    
                    abstract_progress_bar_percentage = (i + 1) / len(entries)
                    abstract_bar.progress(abstract_progress_bar_percentage, text=f"{abstract_progress_text} ({i + 1}/{len(entries)} abstracts processed)")
                
                abstract_bar.empty() # Clear the abstract progress bar

                # Store full document data in session state for access after row selection
                st.session_state["full_documents_data"] = full_documents_data

                # Create a Pandas DataFrame for the main table
                df_table = pd.DataFrame(documents_data_for_table)
                df_sorted = df_table.sort_values(by="Citations", ascending=False).reset_index(drop=True)
                
                st.write("---")
                st.subheader("Publications List")
                # Display the DataFrame with selection enabled
                # 'key' is important for st.dataframe if you have multiple instances or
                # want to preserve state across reruns
                
                # Check if there's a selected row from a previous run to pre-select it
                # if the data is consistent.
                pre_selected_rows = []
                if "selected_document_eid" in st.session_state and st.session_state["selected_document_eid"]:
                    # Find the index of the previously selected EID in the current df_sorted
                    try:
                        selected_index = df_sorted[df_sorted['EID'] == st.session_state["selected_document_eid"]].index[0]
                        pre_selected_rows = [selected_index]
                    except IndexError:
                        # If EID not found (e.g., data changed, or old selection not in new results)
                        pass


                dataframe_response = st.dataframe(
                    df_sorted,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun", # Rerun the app when a row is selected
                    selection_mode="single-row", # Allow only one row to be selected
                    # Set the initial selection based on session state
                    # Streamlit's on_select returns the positional index (0-based)
                    # of the selected row in the current dataframe being displayed.
                    # This means we need to find the index of the EID within the *sorted* DataFrame.
                    # However, direct programmatic selection in st.dataframe is not directly supported
                    # in the way `st.selectbox` allows 'index'. `on_select` is for *reading* selections.
                    # The `pre_selected_rows` logic above is mostly for internal state management,
                    # not directly for forcing UI selection upon reload.
                    # For a truly forced selection in the UI, you'd need custom components like `st-aggrid`.
                    # For now, we'll rely on the user to click.
                )
                
                # Get selected rows from the dataframe response
                selected_rows_indices = dataframe_response.selection.rows

                if selected_rows_indices:
                    # Get the index of the selected row in the *displayed* DataFrame
                    selected_row_index_in_df = selected_rows_indices[0]
                    
                    # Get the actual data of the selected row from the *sorted* DataFrame
                    selected_row_data_summary = df_sorted.iloc[selected_row_index_in_df]
                    selected_eid = selected_row_data_summary['EID']

                    # Store the selected EID in session state
                    st.session_state["selected_document_eid"] = selected_eid

                    # Retrieve the full details using the EID from our pre-processed data
                    selected_doc_full_data = st.session_state["full_documents_data"].get(selected_eid)

                    if selected_doc_full_data:
                        st.write("---")
                        st.subheader(f"Details for Selected Document: {selected_doc_full_data['Title']}")
                        
                        # Use an expander for the abstract and authors for cleaner UI
                        with st.expander("Show Full Abstract and Authors", expanded=True):
                            st.write("**Abstract:**")
                            st.write(selected_doc_full_data['Abstract'])

                            st.write("**Authors:**")
                            if selected_doc_full_data['Authors List']:
                                for author_name in selected_doc_full_data['Authors List']:
                                    st.write(f"- {author_name}")
                            else:
                                st.write("N/A")

                            st.write(f"**First Author:** {selected_doc_full_data['First Author']}")
                            st.write(f"**Corresponding Author:** {selected_doc_full_data['Corresponding Author']}")
                    else:
                        st.warning("Could not retrieve full details for the selected document.")
                else:
                    # If no row is selected, clear the stored EID
                    if "selected_document_eid" in st.session_state:
                        del st.session_state["selected_document_eid"]

                # Download button for the main table data
                st.write("---")
                st.download_button(
                    label="Download Publications List as CSV",
                    data=df_sorted.to_csv(index=False).encode('utf-8'),
                    file_name=f"scopus_publications_{scopus_id_input}.csv",
                    mime="text/csv",
                )