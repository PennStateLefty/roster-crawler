import asyncio
import os
import dotenv
from aiohttp import web, ClientSession
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel import Kernel
from bs4 import BeautifulSoup, Comment

dotenv.load_dotenv()

chat_completion_service = AzureChatCompletion(
    deployment_name=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    service_id="htmlParser",
)

kernel = Kernel()
kernel.add_service(chat_completion_service)
plugins_directory = os.path.join(os.path.dirname(__file__), "prompt_templates")
parser_functions = kernel.add_plugin(parent_directory=plugins_directory, plugin_name="parser_plugins")
roster_parser = parser_functions["roster_parser"]
css_parser = parser_functions["roster_css_class_parser"]

async def escape_html_markup(markup):
    escaped_markup = markup.replace("{", "{{").replace("}", "}}").replace("[", "[[").replace("]", "]]")
    escaped_markup = escaped_markup.replace("'", "\\'").replace('"', '\\"')
    return escaped_markup

async def strip_non_essential_info(html):
    soup = BeautifulSoup(html, 'html.parser')

    # Remove comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove image tags
    for img in soup.find_all('img'):
        img.decompose()

        # Remove all attributes except class
    for tag in soup.find_all(True):  # True finds all tags
        attrs = {key: value for key, value in tag.attrs.items() if key == 'class'}
        tag.attrs = attrs

    return str(soup)

async def retrieve_roster_markup_from_url(url):
    async with ClientSession() as session:
        async with session.get(url) as response:
            html = await response.text()
            cleaned_html = await strip_non_essential_info(html)
            soup = BeautifulSoup(cleaned_html, 'html.parser')       
            
            # Tables should contain the roster information, so if they exist we can move on
            table_elements = soup.find_all(['table'])
            
            #If a table doesn't exist then the layout is likely using CSS classes to display the roster. Use the LLM to extract CSS class names likely associated with the roster
            if len(table_elements) == 0:
                #Get all class names from the HTML
                class_names = set()
                for tag in soup.find_all(True):
                    if tag.has_attr('class'):
                        class_names.update(tag['class'])
                class_list = ', '.join(class_names)
                #Use the LLM to find the CSS class names likely associated with the roster details
                css_candidates = await kernel.invoke(css_parser, class_list=class_list)
                #Assume we got an answer, use that to find the main roster list by the class name
                #TODO: Add error handling for when the LLM doesn't return a valid class name
                candidate_classes = str(css_candidates).split(',')
                #Find roster list elements by the class names
                table_elements = soup.find_all('li', class_=candidate_classes)
                #If no list elements are found, try finding div elements
                if len(table_elements) == 0:
                    table_elements = soup.find_all('div', class_=candidate_classes)
            #TODO: Add a check for table_elements being empty and return an error message if so
            roster_elements = table_elements
            return ''.join(str(element) for element in roster_elements)

async def main():
    url = "https://gopsusports.com/sports/football/roster"
    #url = "https://smumustangs.com/sports/football/roster"
    #url = "https://rolltide.com/sports/football/roster"
    #url = "https://georgiadogs.com/sports/football/roster"
    #url = "https://goheels.com/sports/football/roster"
    #url = "https://texassports.com/sports/football/roster"
    #url = "https://ohiostatebuckeyes.com/sports/football/roster"
    #url = "https://und.com/sports/football/roster"
    markup = await escape_html_markup(await retrieve_roster_markup_from_url(url))
    result = await kernel.invoke(roster_parser, html_markup=markup)
    print(result)

if __name__ == "__main__":
    asyncio.run(main())