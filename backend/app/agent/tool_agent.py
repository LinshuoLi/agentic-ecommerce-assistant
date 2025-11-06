"""Agentic agent with function calling capabilities."""
import re
import logging
from typing import Dict, List, Optional
from app.scraper import PartSelectScraper
from app.llm import DeepseekLLM
from app.config import settings

logger = logging.getLogger(__name__)


class ToolAgent:
    """Agentic agent that uses function calling to let LLM decide what to scrape."""
    
    def __init__(self):
        # Use Playwright scraper (always headless by default)
        try:
            self.scraper = PartSelectScraper(headless=True)
            logger.info("Using Playwright-based scraper (browser automation)")
        except Exception as e:
            logger.error(f"Failed to initialize Playwright scraper: {e}")
            raise
        
        self.llm = DeepseekLLM()
        
        # Register tools with the LLM
        self._register_tools()
    
    def _register_tools(self):
        """Register scraping tools with the LLM."""
        
        # Tool 1: Scrape product page
        self.llm.register_tool(
            name='scrape_product',
            description='MANDATORY: Scrape product information for a part number from PartSelect. ALWAYS call this when you detect a part number (format: PS followed by digits, e.g., PS11752778, PS12345678) in the user query. Returns: product description, installation instructions, compatibility, specifications, appliance type, and URL. Do NOT ask the user for the part number - extract it from their query and call this tool immediately.',
            parameters={
                'type': 'object',
                'properties': {
                    'part_number': {
                        'type': 'string',
                        'description': 'The part number to scrape. Format: PS followed by digits (e.g., PS11752778, PS12345678). Extract this from the user query - do not ask for it.'
                    }
                },
                'required': ['part_number']
            },
            func=self._tool_scrape_product
        )
        
        # Tool 2: Scrape model page
        self.llm.register_tool(
            name='scrape_model',
            description='MANDATORY: Scrape model page for installation instructions and compatibility information. ALWAYS call this when you detect a model number (format: typically 8-15 alphanumeric characters, e.g., WDT780SAEM1, ABC123XYZ) in the user query. Returns: installation instructions, compatible parts, appliance type, description. Do NOT ask the user for the model number - extract it from their query and call this tool immediately.',
            parameters={
                'type': 'object',
                'properties': {
                    'model_number': {
                        'type': 'string',
                        'description': 'The appliance model number to scrape. Format: typically 8-15 alphanumeric characters (e.g., WDT780SAEM1, ABC123XYZ). Extract this from the user query - do not ask for it.'
                    }
                },
                'required': ['model_number']
            },
            func=self._tool_scrape_model
        )
    
    async def _tool_scrape_product(self, part_number: str) -> Dict:
        """Tool function: Scrape product page."""
        try:
            logger.info(f"🔧 Tool called: scrape_product({part_number})")
            product_data = await self.scraper.scrape_product_page(part_number)
            
            if product_data:
                url = product_data.get('url', '')
                result = {
                    'success': True,
                    'part_number': part_number,
                    'title': product_data.get('title', ''),
                    'description': product_data.get('description', ''),
                    'installation_guide': product_data.get('installation_guide', ''),
                    'appliance_type': product_data.get('appliance_type'),
                    'compatibility': product_data.get('compatibility', []),
                    'url': url,
                    'specifications': product_data.get('specifications', {})
                }
                logger.info(f"✅ Scraped product {part_number}: {result.get('title', 'N/A')[:50]}...")
                # Store URL for later collection (will be extracted by LLM wrapper)
                if url:
                    result['_source_url'] = url
                return result
            else:
                logger.warning(f"⚠️  Could not scrape product {part_number}")
                return {
                    'success': False,
                    'error': f'Could not find product page for {part_number}. Please verify the part number is correct.'
                }
        except Exception as e:
            logger.error(f"❌ Error in scrape_product tool: {e}")
            return {
                'success': False,
                'error': f'Scraping error: {str(e)}'
            }
    
    async def _tool_scrape_model(self, model_number: str) -> Dict:
        """Tool function: Scrape model page."""
        try:
            logger.info(f"🔧 Tool called: scrape_model({model_number})")
            model_data = await self.scraper.scrape_model_page(model_number)
            
            if model_data:
                url = model_data.get('url', '')
                result = {
                    'success': True,
                    'model_number': model_number,
                    'title': model_data.get('title', ''),
                    'description': model_data.get('description', ''),
                    'instructions': model_data.get('instructions', ''),
                    'appliance_type': model_data.get('appliance_type'),
                    'compatible_parts': model_data.get('compatible_parts', []),
                    'url': url
                }
                logger.info(f"✅ Scraped model {model_number}: {result.get('title', 'N/A')[:50]}...")
                # Store URL for later collection (will be extracted by LLM wrapper)
                if url:
                    result['_source_url'] = url
                return result
            else:
                logger.warning(f"⚠️  Could not scrape model {model_number}")
                return {
                    'success': False,
                    'error': f'Could not find model page for {model_number}. Please verify the model number is correct.'
                }
        except Exception as e:
            logger.error(f"❌ Error in scrape_model tool: {e}")
            return {
                'success': False,
                'error': f'Scraping error: {str(e)}'
            }
    
    async def process_query(self, query: str, conversation_history: Optional[List[Dict]] = None, feedback_insights: Optional[Dict] = None) -> Dict:
        """Process a user query using agentic function calling."""
        try:
            # Check if query is out of scope
            if self._is_out_of_scope(query):
                return {
                    'response': self._get_out_of_scope_response(),
                    'intent': 'out_of_scope',
                    'entities': {},
                    'sources_used': 0
                }
            
            # Extract entities for reporting 
            entities = self._extract_entities(query)
            intent = self._analyze_intent(query)
            
            # Prepare base system prompt with explicit extraction guidance
            base_system_prompt = """You are a helpful assistant for PartSelect, an e-commerce website specializing in appliance parts, specifically Refrigerators and Dishwashers.

CRITICAL: You MUST extract part numbers and model numbers from user queries and use them to scrape information.

PART NUMBER FORMAT: PS followed by digits (e.g., PS11752778, PS12345678)
MODEL NUMBER FORMAT: Typically 8-15 alphanumeric characters (e.g., WDT780SAEM1, ABC123XYZ)

YOUR WORKFLOW:
1. When you see a part number (PS followed by numbers) in the query:
   - IMMEDIATELY call scrape_product(part_number) to get ALL information
   - Do NOT ask the user for more information - SCRAPE IT YOURSELF
   
2. When you see a model number (8-15 alphanumeric chars) in the query:
   - IMMEDIATELY call scrape_model(model_number) to get installation instructions and compatibility
   - Do NOT ask the user for more information - SCRAPE IT YOURSELF

3. If the query mentions both part and model numbers:
   - Call BOTH tools: scrape_product() AND scrape_model()
   - Compare compatibility information

4. When user asks for a part BY NAME (e.g., "Upper Rack Adjuster Kit", "Door Gasket", "Water Filter"):
   - If you have scraped model data with compatible_parts, SEARCH through that list FIRST
   - Look for part names/descriptions that match the user's request
   - Extract the part_number from matching compatible_parts entries
   - If you find a matching part number, call scrape_product(part_number) to get full details
   - ALWAYS provide the actual part number (PS + digits) when you find it
   - NEVER say "I need to search" or "I need more details" - DO THE SEARCH YOURSELF

5. After scraping, use the scraped data to provide a complete answer with actual part numbers

AVAILABLE TOOLS:
- scrape_product(part_number): Scrape product page for description, installation guide, compatibility, specifications
  Example: scrape_product("PS11752778")
  
- scrape_model(model_number): Scrape model page for installation instructions, compatible parts, appliance type
  Example: scrape_model("WDT780SAEM1")

MANDATORY RULES:
1. If you detect a part number (PS + digits) → MUST call scrape_product()
2. If you detect a model number (8-15 alphanumeric) → MUST call scrape_model()
3. When user asks for a part by name, search compatible_parts from scraped model data FIRST
4. If you find a part in compatible_parts, extract the part_number and scrape it
5. NEVER ask the user for information you can get by scraping or searching
6. NEVER say "I need to search" or "I need more details" - DO THE SEARCH YOURSELF
7. ALWAYS provide actual part numbers (PS + digits) when you find them
8. NEVER say "I couldn't find information" without calling the scraping tools first
9. Provide complete answers based on scraped data, not assumptions

EXAMPLES:
User: "PS11752778?" 
→ You: Call scrape_product("PS11752778"), then answer based on scraped data

User: "How to install WDT780SAEM1?"
→ You: Call scrape_model("WDT780SAEM1"), then provide installation instructions from scraped data

User: "Is PS11752778 compatible with WDT780SAEM1?"
→ You: Call scrape_product("PS11752778") AND scrape_model("WDT780SAEM1"), then compare compatibility

User: "I need an Upper Rack Adjuster Kit" (after model WDT780SAEM1 was scraped)
→ You: Check compatible_parts from scraped model data, find entry matching "Upper Rack Adjuster Kit",
   extract part_number (e.g., PS12345678), call scrape_product("PS12345678"), provide full details with part number

Always extract and use part/model numbers from queries - never ask the user for them!
When compatible_parts are available, search through them to find part numbers by name!

IMPORTANT - SOURCE LINKS:
- When you use scraped data, ALWAYS mention the source URL at the end of your response
- Format: "Source: [URL]" or "Learn more: [URL]"
- Include ALL source URLs you used (both product and model pages if applicable)
- Make URLs clickable in markdown format: [link text](URL)"""
            
            # Enhance system prompt with feedback-based improvements if available
            from app.feedback_analyzer import feedback_analyzer
            if feedback_insights:
                system_prompt = feedback_analyzer.enhance_system_prompt(base_system_prompt, feedback_insights)
            else:
                system_prompt = base_system_prompt
            
            # Prepare messages
            messages = [
                {'role': 'system', 'content': system_prompt}
            ]
            
            # Add conversation history
            if conversation_history:
                for msg in conversation_history[-5:]:
                    messages.append({
                        'role': msg.get('role', 'user'),
                        'content': msg.get('content', '')
                    })
            
            # Add current query
            messages.append({'role': 'user', 'content': query})
            
            # Add explicit hint if entities are detected but LLM might miss them
            if entities.get('part_numbers') or entities.get('model_numbers'):
                hint = "\n\nDETECTED IN QUERY:\n"
                if entities.get('part_numbers'):
                    hint += f"- Part number(s): {', '.join(entities['part_numbers'])} - YOU MUST call scrape_product() for each\n"
                if entities.get('model_numbers'):
                    hint += f"- Model number(s): {', '.join(entities['model_numbers'])} - YOU MUST call scrape_model() for each\n"
                hint += "Do NOT ask the user for these - they are already in the query. Call the scraping tools NOW!"
                messages[-1]['content'] += hint
            
            # Use chat with tools - LLM will decide what to scrape
            # Track source URLs from tool calls
            source_urls = []
            response = await self.llm.chat_with_tools(messages, max_iterations=10, collect_urls=source_urls)
            
            # Remove duplicate URLs
            source_urls = list(dict.fromkeys(source_urls))  # Preserves order
            
            return {
                'response': response,
                'intent': intent,
                'entities': entities,
                'sources_used': len(source_urls),
                'source_urls': source_urls
            }
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                'response': "I apologize, but I encountered an error processing your request. Please try again.",
                'error': str(e)
            }
    
    def _extract_entities(self, query: str) -> Dict:
        """Extract entities from query."""
        entities = {
            'part_numbers': [],
            'model_numbers': [],
            'appliance_type': None
        }
        
        # Extract part numbers
        part_numbers = re.findall(r'PS\d+', query, re.I)
        entities['part_numbers'] = list(set(part_numbers))
        
        # Extract model numbers
        model_pattern = r'\b[A-Z0-9]{8,15}\b'
        potential_models = re.findall(model_pattern, query)
        entities['model_numbers'] = [
            m for m in potential_models 
            if not m.startswith('PS') and len(m) >= 8
        ]
        
        # Detect appliance type
        query_lower = query.lower()
        if 'refrigerator' in query_lower or 'fridge' in query_lower:
            entities['appliance_type'] = 'refrigerator'
        elif 'dishwasher' in query_lower:
            entities['appliance_type'] = 'dishwasher'
        
        return entities
    
    def _analyze_intent(self, query: str) -> str:
        """Analyze query intent."""
        query_lower = query.lower()
        
        if any(word in query_lower for word in ['install', 'installation', 'how to install']):
            return 'installation'
        elif any(word in query_lower for word in ['compatible', 'compatibility', 'fit']):
            return 'compatibility'
        elif any(word in query_lower for word in ['fix', 'repair', 'troubleshoot', 'not working']):
            return 'troubleshooting'
        else:
            return 'general'
    
    def _is_out_of_scope(self, query: str) -> bool:
        """Check if query is out of scope."""
        query_lower = query.lower()
        
        out_of_scope_keywords = [
            'washing machine', 'dryer', 'oven', 'stove', 'microwave',
            'air conditioner', 'heater', 'vacuum'
        ]
        
        mentions_out_of_scope = any(keyword in query_lower for keyword in out_of_scope_keywords)
        mentions_in_scope = 'refrigerator' in query_lower or 'fridge' in query_lower or 'dishwasher' in query_lower
        
        if mentions_out_of_scope and not mentions_in_scope:
            return True
        
        unrelated_topics = ['weather', 'news', 'sports', 'politics', 'cooking recipe']
        if any(topic in query_lower for topic in unrelated_topics):
            return True
        
        return False
    
    def _get_out_of_scope_response(self) -> str:
        """Get response for out-of-scope queries."""
        return """I'm a specialized assistant for PartSelect, focusing on Refrigerator and Dishwasher parts. 

I can help you with:
- Product information and part numbers
- Compatibility checks between parts and appliance models
- Installation instructions
- Troubleshooting common issues

If you have questions about other appliances or topics outside this scope, I recommend contacting PartSelect customer service directly."""

