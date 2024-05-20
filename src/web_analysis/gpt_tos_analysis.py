from gpt import GPT
import asyncio
import json
import re
import pickle
from tqdm import tqdm
import csv
import argparse
import ijson

async def stream_and_process(file_path, gpt_instance, prompt_key, filter_keywords, filter_domain_type, batch_size=10):
    """
    Asynchronously streams and processes Terms of Service (ToS) documents from a JSON file, using an instance of GPT to analyze the content.
    Documents are processed in batches to optimize performance.

    Parameters:
    - file_path (str): The path to the JSON file containing the ToS documents.
    - gpt_instance: An instance of the GPT model used to process the document text.
    - prompt_key (str): The prompt key used to determine the relevance of the text.
    - filter_keywords (bool): A flag indicating whether to filter documents based on keywords before sending them to GPT.
    - batch_size (int, optional): The size of the batches in which documents are processed. Defaults to 10.

    Returns:
    - final_responses (list): A list of dictionaries containing the results of the processing. Each dictionary includes the domain,
      ToS link, date, and either the GPT response or a verdict and evidence if the document was deemed irrelevant.
    """
    batch = []
    final_responses = []
    domain_docs = {}

    with tqdm(desc="Processing documents", unit="doc") as pbar:
        for entry in stream_json(file_path):
            domain, tos_link, date, text = entry
            if domain not in domain_docs:
                domain_docs[domain] = []
            domain_docs[domain].append((tos_link, date, text))
            pbar.update(1)
    
    for domain, docs in domain_docs.items():
        filtered_docs, all_privacy = filter_docs_by_domain_type(docs) if filter_domain_type else (docs, False)
        if all_privacy:
            for tos_link, date, text in docs:
                final_responses.append({
                    "domain": domain,
                    "tos_link": tos_link,
                    "date": date,
                    "verdict": "False",
                    "evidence": "N/A"
                })
        else:
            for tos_link, date, text in filtered_docs:
                cleaned_text = clean_text(text)
                if filter_keywords and not is_relevant(cleaned_text, prompt_key):
                    final_responses.append({
                        "domain": domain,
                        "tos_link": tos_link,
                        "date": date,
                        "verdict": "False",
                        "evidence": "N/A"
                    })
                else:
                    prompt = {
                        "text": cleaned_text,
                        "metadata": {
                            "domain": domain,
                            "tos_link": tos_link,
                            "date": date
                        }
                    }
                    batch.append(prompt)
                    if len(batch) >= batch_size:
                        responses = await gpt_instance.process_prompts_in_batches_async(batch)
                        final_responses.extend([
                            {**prompt['metadata'], **response} for prompt, response in zip(batch, responses)
                        ])
                        batch = []
    
    if batch:
        responses = await gpt_instance.process_prompts_in_batches_async(batch)
        final_responses.extend([
            {**prompt['metadata'], **response} for prompt, response in zip(batch, responses)
        ])

    return final_responses

async def process_sample(data, gpt_instance, prompt_key, filter_keywords, filter_domain_type, batch_size=10):
    """
    Asynchronously processes a sample of Terms of Service (ToS) documents, using an instance of GPT to analyze the content.
    Documents are processed in batches to optimize performance.

    Parameters:
    - data (list): A list of tuples, each containing domain, tos_link, date, and text of a ToS document.
    - gpt_instance: An instance of the GPT model used to process the document text.
    - prompt_key (str): The prompt key used to determine the relevance of the text.
    - filter_keywords (bool): A flag indicating whether to filter documents based on keywords before sending them to GPT.
    - batch_size (int, optional): The size of the batches in which documents are processed. Defaults to 10.

    Returns:
    - final_responses (list): A list of dictionaries containing the results of the processing. Each dictionary includes the domain,
      ToS link, date, and either the GPT response or a verdict and evidence if the document was deemed irrelevant.
    """
    batch = []
    final_responses = []
    domain_docs = {}

    for entry in tqdm(data, desc="Processing TOS docs"):
        domain, tos_link, date, text = entry
        if domain not in domain_docs:
            domain_docs[domain] = []
        domain_docs[domain].append((tos_link, date, text))
    
    for domain, docs in domain_docs.items():
        filtered_docs, all_privacy = filter_docs_by_domain_type(docs) if filter_domain_type else (docs, False)
        if all_privacy:
            for tos_link, date, text in docs:
                final_responses.append({
                    "domain": domain,
                    "tos_link": tos_link,
                    "date": date,
                    "verdict": "False",
                    "evidence": "N/A"
                })
        else:
            for tos_link, date, text in filtered_docs:
                cleaned_text = clean_text(text)
                if filter_keywords and not is_relevant(cleaned_text, prompt_key):
                    final_responses.append({
                        "domain": domain,
                        "tos_link": tos_link,
                        "date": date,
                        "verdict": "False",
                        "evidence": "N/A"
                    })
                else:
                    prompt = {
                        "text": cleaned_text,
                        "metadata": {
                            "domain": domain,
                            "tos_link": tos_link,
                            "date": date
                        }
                    }
                    batch.append(prompt)
                    if len(batch) >= batch_size:
                        responses = await gpt_instance.process_prompts_in_batches_async(batch)
                        final_responses.extend([
                            {**prompt['metadata'], **response} for prompt, response in zip(batch, responses)
                        ])
                        batch = []
    
    if batch:
        responses = await gpt_instance.process_prompts_in_batches_async(batch)
        final_responses.extend([
            {**prompt['metadata'], **response} for prompt, response in zip(batch, responses)
        ])

    return final_responses

def filter_docs_by_domain_type(docs):
    non_privacy_docs = [doc for doc in docs if "privacy" not in doc[0].lower()]
    if non_privacy_docs:
        return non_privacy_docs, False
    return docs, True

def clean_text(text):
    """
    Clean text by removing unwanted characters and normalizing whitespace.

    Parameters:
    - text (str): The text to clean.

    Returns:
    - str: The cleaned text.
    """
    cleaned_text = re.sub(r'[\t\n\r]+', ' ', text)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    return cleaned_text

def is_relevant(text, prompt_key):
    """Check if the text contains any of the specified keywords.
        Parameters:
    - text (str): The text to check for keywords.

    Returns:
    - bool: True if a keyword is found, flase if not.
    """
    keyword_dict = {'scraping': ["Scrape", "harvest", "extract", "Web scraping", "Web Crawler", "spiders", "scripts", "crawler","Archival", "Machine-readable data", "Metadata", "Crawling", "Indexing", "Sitemaps", "Robots.txt", "Descriptive metadata", "Keyword research", "Timeliness of content", "Last modified", "HTTP headers", "Automated web scraping", "CAPTCHAs", "Denial-of-service attack", "data gathering", "extraction methods", "public search engine", "API", "data extraction"],
                'AI-policy': ["machine learning", "ML", "artificial intelligence", "AI", "system", "training", "software", "program", "data sets", "generative", "models", "GPTBot user agent", "API"],
                'competing-services': ["Commercial Use", "display", "distribute", "license", "publish", "reproduce", "duplicate", "copy", "create derivative works from", "modify", "sell", "resell", "exploit", "transfer", "commercial", "buying", "exchanging", "selling", "promotion"],
                'illicit-content': ["unlawful", "threatening", "abusive", "harassing", "defamatory", "libelous", "deceptive", "fraudulent", "invasive of another's privacy", "tortious", "obscene", "vulgar", "pornographic", "offensive", "profane", "contains", "depicts nudity", "contains", "depicts sexual activity", "inappropriate", "criminal"],
                'type-of-license': ["property", "respective owners", "copyright", "trademark", "subsidiaries", "affiliates", "assigns", "licensors", "without limitation", "creative", "transmit", "transfer", "sale", "sell", "derivative works", "amalgamated"]
            }
    keywords = None

    for key in keyword_dict:
        if key in prompt_key:
            keywords = keyword_dict[key]
            break

    # reg. ex. pattern
    keyword_pattern = re.compile(r'\b(' + '|'.join(map(re.escape, keywords)) + r')\b', re.IGNORECASE)
    match = keyword_pattern.search(text)

    return bool(match)

def open_sampled_data(sample_file_path):
    """
    Opens and loads data from a pickled file specified by the file path. This function is designed to handle 
    the file operations for reading binary data, specifically using the pickle module to deserialize objects 
    stored in files.

    Parameters:
        sample_file_path (str): The path to the file containing the pickled data.

    Returns:
        object: The data unpickled from the file if successful.
    """
    try:
        with open(sample_file_path, 'rb') as f:
            sampled_data = pickle.load(f)
            print("Sample data successfully loaded!")
            # re-formatting sampled data to new format
            data = []
            for parent_domain, tos_list in sampled_data.items():
                for tos_link, date, text in tos_list:
                    data.append((parent_domain,tos_link,date,text))
            return data
    except FileNotFoundError:
        print(f"Error: The file {sample_file_path} does not exist.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def format_for_json(final_responses):
    """
    Formats the final responses for JSON serialization. Transforms the data structure to organize responses
    by domain, ToS link, and date.

    Parameters:
    - final_responses (list): A list of dictionaries containing the results of the processing. Each dictionary includes the domain,
      ToS link, date, verdict, and evidence.

    Returns:
    - transformed_data (dict): A nested dictionary where the top-level keys are domains, the second-level keys are ToS links,
      and the third-level keys are dates. Each entry contains the verdict and evidence.
    """
    transformed_data = {}
    for entry in final_responses:        
        domain = entry["domain"]
        link = entry["tos_link"]
        date = entry["date"]
        
        # Check if 'verdict' and 'evidence' keys exist in entry
        if 'verdict' not in entry or 'evidence' not in entry:
            print(f"Skipping entry due to missing 'verdict' or 'evidence': {entry}")
            continue
        
        verdict_info = {
            "verdict": entry["verdict"],
            "evidence": entry["evidence"]
        }

        if domain not in transformed_data:
            transformed_data[domain] = {}
        if link not in transformed_data[domain]:
            transformed_data[domain][link] = {}
        
        transformed_data[domain][link][date] = verdict_info

    return transformed_data


def save_json_output(json_data, file_name):
    """
    Save the final JSON data to a file.

    Parameters:
    - json_data (dict): The formatted JSON data to be saved.
    - file_name (str): The name of the file to save the JSON data to.

    Returns:
    - None: Writes data directly to a JSON file.
    """
    with open(file_name, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)
    print(f"Data successfully saved to {file_name}")
    
def save_binary_output_to_csv(formatted_data, prompt_key):
    """
    Save aggregated verdicts and evidence for up to five TOS links per domain to a CSV file.

    Parameters:
    - formatted_data (dict): A dictionary with domains as keys and nested dictionaries of TOS links and their respective verdicts and evidence.
    - prompt_key (str): The key for the specific prompt used in GPT processing.

    Returns:
    - None: Writes data directly to a CSV file.
    """
    file_name = f'data/{prompt_key}-gpt-domain-filtering.csv'  

    question_dict = {'scraping': 'Does the website restrict scraping? [True/False]',
                     'AI-policy': 'Does website have specific restrictions related to AI training? [True/False]', 
                     'competing-services': 'Does website restrict use of content for competing services? [True/False]',
                     'illicit-content': 'Does website restrict posting illicit content? [True/False]', 
                     'type-of-license': 'What may website content be used for?',
                    }
    
    question = None
    for key in question_dict:
        if key in prompt_key:
            question = question_dict[key]
            break

    headers = ['Domain', 'TOS link 1', 'TOS link 2', 'TOS link 3', 'TOS link 4', 'TOS link 5', question, 'Evidence']

    with open(file_name, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(headers)

        for domain, links in formatted_data.items():
            links_list = list(links.items())[:5]  # select up to the first five links
            link_columns = [link for (link, _) in links_list] + [None] * (5 - len(links_list))
            all_verdicts = []
            all_evidence = []

            for _, dates in links.items():
                for date_info in dates.values():
                    all_verdicts.append(date_info['verdict'] == "True")
                    if date_info['verdict'] == "True":
                        all_evidence.append(date_info['evidence'])

            aggregated_verdict = any(all_verdicts)
            aggregated_evidence = " | ".join(all_evidence)

            row = [domain] + link_columns + [aggregated_verdict, aggregated_evidence]
            writer.writerow(row)

def save_non_binary_output_to_csv(formatted_data, prompt_key):
    """
    Save aggregated verdicts and evidence for up to five TOS links per domain to a CSV file,
    categorizing the explicitness and conditions of scraping policies.

    Parameters:
    - formatted_data (dict): A dictionary with domains as keys and nested dictionaries of TOS links and their respective verdicts and evidence.
    - prompt_key (str): The key for the specific prompt used in GPT processing.

    Returns:
    - None: Writes data directly to a CSV file.
    """
    file_name = f'data/{prompt_key}-gpt-no-keyword-filtering.csv' 
    question_dict = {'scraping': 'Does the website restrict scraping? [True/False]',
                     'type-of-license': 'What may website content be used for?',
                    }

    question = None
    for key in question_dict:
        if key in prompt_key:
            question = question_dict[key]
            break

    headers = ['Domain', 'TOS link 1', 'TOS link 2', 'TOS link 3', 'TOS link 4', 'TOS link 5', question, 'Evidence']

    with open(file_name, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(headers)

        for domain, links in formatted_data.items():
            links_list = list(links.items())[:5]  # select up to the first five links
            link_columns = [link for (link, _) in links_list] + [None] * (5 - len(links_list))
            verdicts_collected = []

            for _, dates in links.items():
                for date_info in dates.values():
                    verdict = date_info['verdict']
                    evidence = date_info['evidence']
                    verdicts_collected.append((verdict, evidence))

            # determine the final verdict 
            if any(v == "Prohibited" for v, _ in verdicts_collected):
                final_verdict = "Prohibited"
            elif any(v == "Allowed" for v, _ in verdicts_collected):
                final_verdict = "Allowed"
            elif any(v == "Conditional" for v, _ in verdicts_collected):
                final_verdict = "Conditional"
            else:
                final_verdict = "Not mentioned"

            aggregated_evidence = " | ".join([f"{v}: {e}" for v, e in verdicts_collected if v != "Not mentioned"])

            row = [domain] + link_columns + [final_verdict, aggregated_evidence]
            writer.writerow(row)

##################################################################################

def main(custom_sample, sample_file_path, prompt_key, save_verdicts, filter_keywords, filter_domain_type):
    if prompt_key is None:
        raise ValueError("prompt_key must be provided. Options are: 'scraping-policy', 'AI-policy', 'competing-services', 'illicit-content', 'type-of-license', 'scraping-policy-keywords', 'AI-policy-keywords', 'competing-services-keywords', 'illicit-content-keywords', 'type-of-license-keywords'")
    
    gpt_4o = GPT(model='gpt-4o', prompt=prompt_key)
    print(f"System Instructions: {gpt_4o.get_system_prompt()}\nChat GPT dialouge:\nUser: {gpt_4o.get_user_prompt1()}\nGPT: {gpt_4o.get_assistant_prompt1()}\nUser: {gpt_4o.get_guidelines_prompt()}")

    if custom_sample:
        if not sample_file_path:
            raise ValueError("sample_file_path must be provided if custom_sample is set to True.")
        data = open_sampled_data(sample_file_path)
        results = asyncio.run(process_sample(data, gpt_4o, prompt_key, filter_keywords, filter_domain_type))
        json_data = format_for_json(results)
    else:
        # stream whole dataset
        results = stream_and_process('path-to-data', gpt_4o, prompt_key, filter_keywords, filter_domain_type)
        json_data = format_for_json(results)

    if save_verdicts:
        save_binary_output_to_csv(json_data,prompt_key) # change depending on prompt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--custom_sample', type=bool, default=False, help='Use a custom sample file. Must be a .pkl file in correct format.')
    parser.add_argument('--sample_file_path', type=str, default='', help='Path to the sample file')
    # parser.add_argument('--sample_size', type=int, default=10, help='Size of the sample to generate')
    # parser.add_argument('--save_sample', type=bool, default=False, help='Save the sampled data to .pkl file')
    parser.add_argument('--prompt_key', type=str, default=None, help='Prompt key for GPT model. Options are: \"scraping-policy\", \"AI-policy\", \"competing-services\", \"illicit-content\", \"type-of-license\", \"scraping-policy-keywords\", \"AI-policy-keywords\", \"competing-services-keywords\", \"illicit-content-keywords\", \"type-of-license-keywords\"')
    parser.add_argument('--save_verdicts', type=bool, default=True, help='Save the generated verdicts to .csv file') # change to json
    parser.add_argument('--filter_keywords', type=bool, default=False, help='Filter out documents that do not contain keywords.') 
    parser.add_argument('--filter_domain_type', type=bool, default=False, help='Filter out documents with "privacy" in the URL if other ToS pages exist for the same domain.')


    args = parser.parse_args()
    
    main(args.custom_sample, args.sample_file_path, args.prompt_key, args.save_verdicts, args.filter_keywords, args.filter_domain_type)