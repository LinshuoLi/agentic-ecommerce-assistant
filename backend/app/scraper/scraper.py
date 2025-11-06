"""Web scraper for PartSelect website using Playwright browser automation."""
import asyncio
import re
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class PartSelectScraper:
    """Playwright-based scraper that uses browser automation to interact with PartSelect search."""
    
    def __init__(self, headless: bool = True):
        self.base_url = settings.partselect_base_url
        self.delay = settings.scraper_delay
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None
        self._initialized = False
        self._init_lock = None  # Will be created lazily in async context
        # Don't initialize here - wait until first async method call
    
    async def _ensure_initialized(self):
        """Ensure browser is initialized (lazy initialization)."""
        if self._initialized and self.page:
            return
        
        # Create lock lazily if needed
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        
        async with self._init_lock:
            # Check again after acquiring lock
            if self._initialized and self.page:
                return
            
            await self._init_browser()
    
    async def _init_browser(self):
        """Initialize Playwright browser."""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                ]
            )
            
            # Create a new context with custom settings
            context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            # Create a new page
            self.page = await context.new_page()
            
            # Remove webdriver property detection
            await self.page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Set default timeout
            self.page.set_default_timeout(30000)  # 30 seconds
            self.page.set_default_navigation_timeout(30000)
            
            self._initialized = True
            logger.info("Playwright browser initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Playwright browser: {e}")
            logger.warning("Browser automation not available")
            self.browser = None
            self.page = None
            self._initialized = False
            raise
    
    async def close(self):
        """Cleanup browser."""
        try:
            if self.page:
                await self.page.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self._initialized = False
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
    
    async def search_and_get_product(self, part_number: str) -> Optional[Dict]:
        """Search for part number using the search bar and get product information."""
        await self._ensure_initialized()
        
        if not self.page:
            logger.warning("Playwright page not available")
            return None
        
        try:
            # Navigate to PartSelect
            logger.info(f"Navigating to PartSelect to search for {part_number}...")
            try:
                await self.page.goto(self.base_url, wait_until='domcontentloaded', timeout=30000)
            except PlaywrightTimeoutError:
                logger.warning("Page load timeout, continuing anyway...")
                # Stop loading
                await self.page.evaluate("window.stop()")
            await asyncio.sleep(1)
            
            # Find the search bar - use the exact ID from the HTML you found
            # From your inspection: <input id="searchboxInput" ...>
            search_selectors = [
                "input#searchboxInput",  # Exact ID from your HTML
                "input[id='searchboxInput']",
                "input[name='SearchTerm']",
                "input[placeholder*='Search']",
                "input[type='search']",
                "#searchboxInput",
            ]
            
            search_input = None
            for selector in search_selectors:
                try:
                    # Wait for element to be visible and clickable
                    search_input = await self.page.wait_for_selector(selector, state='visible', timeout=10000)
                    if search_input:
                        logger.info(f"Found search bar with selector: {selector}")
                        break
                except PlaywrightTimeoutError:
                    continue
            
            if not search_input:
                logger.error("Could not find search bar")
                return None
            
            # Scroll to element to ensure it's in view
            await search_input.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            
            # Fill in the search input and submit
            try:
                # Click to focus, then fill (fill() replaces existing content, no need for clear())
                await search_input.click()
                await search_input.fill(part_number)
                await asyncio.sleep(0.5)
                await search_input.press('Enter')
            except Exception as e:
                logger.warning(f"Direct interaction failed, using JavaScript: {e}")
                # Fallback: use JavaScript to set value and submit
                self.page.evaluate(f"""
                    (function() {{
                        const input = document.querySelector('{selector}');
                        if (input) {{
                            input.value = '{part_number}';
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            // Try to find and click submit button
                            const submitBtn = document.querySelector('button.js-searchBtn, button[type="submit"]');
                            if (submitBtn) {{
                                submitBtn.click();
                            }} else {{
                                input.form?.submit();
                            }}
                        }}
                    }})();
                """)
                await asyncio.sleep(0.5)
            
            # Wait for page to load (either redirect or search results)
            await asyncio.sleep(3)
            
            # Wait for URL to change or page to load
            try:
                base_url = self.base_url
                await self.page.wait_for_function(
                    f"() => window.location.href !== '{base_url}'",
                    timeout=10000
                )
            except PlaywrightTimeoutError:
                logger.warning("Page did not navigate after search")
            
            # Check if we're on a product page (direct match) or search results
            current_url = self.page.url
            
            # If URL contains the part number and .htm, likely a product page
            if part_number.replace('PS', '') in current_url and '.htm' in current_url:
                logger.info(f"Direct product page found: {current_url}")
                return await self._scrape_product_page_from_playwright(current_url, part_number)
            
            # Otherwise, look for product link in search results
            logger.info("Search results page, looking for product link...")
            product_link = await self._find_product_link_in_results(part_number)
            
            if product_link:
                logger.info(f"Found product link: {product_link}")
                try:
                    await self.page.goto(product_link, wait_until='domcontentloaded', timeout=30000)
                except PlaywrightTimeoutError:
                    logger.warning("Page load timeout for product page, continuing anyway...")
                    await self.page.evaluate("window.stop()")
                await asyncio.sleep(2)
                return await self._scrape_product_page_from_playwright(product_link, part_number)
            else:
                logger.warning(f"Could not find product link for {part_number} in search results")
                return None
                
        except Exception as e:
            logger.error(f"Error in Playwright search: {e}")
            return None
    
    async def _find_product_link_in_results(self, part_number: str) -> Optional[str]:
        """Find product link in search results page."""
        try:
            # Look for links containing the part number
            part_num_only = part_number.replace('PS', '')
            
            # Try multiple selectors for product links
            link_selectors = [
                f"a[href*='{part_number}']",
                f"a[href*='{part_num_only}']",
                "a[href*='/PS']",
                ".product-link",
                ".result-item a",
                "[data-part-number]"
            ]
            
            for selector in link_selectors:
                try:
                    links = await self.page.locator(selector).all()
                    for link in links:
                        href = await link.get_attribute('href')
                        if href and (part_number in href or part_num_only in href):
                            # Make sure it's a product page (.htm)
                            if '.htm' in href:
                                # Make absolute URL if needed
                                if href.startswith('/'):
                                    href = self.base_url + href
                                return href
                except:
                    continue
            
            # Fallback: get all links and filter by text content or href
            logger.info("Fallback: Checking all links on page...")
            all_links = await self.page.locator('a').all()
            logger.info(f"Found {len(all_links)} total links on page")
            
            for link in all_links:
                try:
                    href = await link.get_attribute('href')
                    if href:
                        # Normalize href
                        if href.startswith('/'):
                            href = self.base_url + href
                        # Check for part number match (be more flexible)
                        if (part_num_only in href or part_number in href) and ('.htm' in href or '/PS' in href):
                            logger.info(f"Found matching product link in fallback: {href}")
                            return href
                except Exception as e:
                    logger.debug(f"Error checking link: {e}")
                    continue
            
            logger.warning(f"No product link found for {part_number} in search results")
            return None
            
        except Exception as e:
            logger.error(f"Error finding product link: {e}")
            return None
    
    async def _extract_product_data_with_bs4(self, html_content: str, part_number: str, url: str) -> Dict:
        """Use BeautifulSoup to extract structured product data from HTML."""
        product_data = {
            'part_number': part_number,
            'url': url,
            'title': '',
            'description': '',
            'appliance_type': None,
            'compatibility': [],
            'installation_guide': '',
            'specifications': {},
            'related_parts': []
        }
        
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Extract title from h1 or page title
            title_elem = soup.find('h1')
            if title_elem:
                product_data['title'] = title_elem.get_text(strip=True)
            else:
                title_tag = soup.find('title')
                if title_tag:
                    product_data['title'] = title_tag.get_text(strip=True)
            
            # Extract description - look for common description selectors
            description_selectors = [
                '.product-description',
                '.description',
                '#description',
                '[class*="description"]',
                'meta[name="description"]'
            ]
            
            for selector in description_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    if desc_elem.name == 'meta':
                        product_data['description'] = desc_elem.get('content', '')
                    else:
                        product_data['description'] = desc_elem.get_text(strip=True)
                    if product_data['description']:
                        break
            
            # Determine appliance type from title or description
            text_to_check = (product_data.get('title', '') + ' ' + product_data.get('description', '')).lower()
            if 'refrigerator' in text_to_check or 'fridge' in text_to_check:
                product_data['appliance_type'] = 'refrigerator'
            elif 'dishwasher' in text_to_check:
                product_data['appliance_type'] = 'dishwasher'
            
            # Extract installation guide - look for installation-related sections
            install_selectors = [
                '.installation-guide',
                '.installation',
                '#installation',
                '[class*="installation"]',
                '[id*="installation"]'
            ]
            
            for selector in install_selectors:
                install_elem = soup.select_one(selector)
                if install_elem:
                    product_data['installation_guide'] = install_elem.get_text(strip=True)
                    if product_data['installation_guide']:
                        break
            
            # Extract compatibility information - look for compatibility lists
            compat_selectors = [
                '.compatibility',
                '.compatible-models',
                '[class*="compat"]',
                '[id*="compat"]'
            ]
            
            for selector in compat_selectors:
                compat_elem = soup.select_one(selector)
                if compat_elem:
                    # Extract list items or links
                    items = compat_elem.find_all(['li', 'a', 'span'])
                    for item in items:
                        text = item.get_text(strip=True)
                        if text and len(text) > 2:
                            product_data['compatibility'].append(text)
                    if product_data['compatibility']:
                        break
            
            # Extract specifications - look for specification tables or lists
            spec_selectors = [
                '.specifications',
                '.specs',
                'table.specifications',
                '[class*="spec"]',
                'dl'  # definition lists are often used for specs
            ]
            
            for selector in spec_selectors:
                spec_elem = soup.select_one(selector)
                if spec_elem:
                    # Try to parse as table
                    if spec_elem.name == 'table':
                        rows = spec_elem.find_all('tr')
                        for row in rows:
                            cells = row.find_all(['td', 'th'])
                            if len(cells) >= 2:
                                key = cells[0].get_text(strip=True)
                                value = cells[1].get_text(strip=True)
                                if key and value:
                                    product_data['specifications'][key] = value
                    # Try to parse as definition list
                    elif spec_elem.name == 'dl':
                        dt_elements = spec_elem.find_all('dt')
                        dd_elements = spec_elem.find_all('dd')
                        for dt, dd in zip(dt_elements, dd_elements):
                            key = dt.get_text(strip=True)
                            value = dd.get_text(strip=True)
                            if key and value:
                                product_data['specifications'][key] = value
                    # Try to parse as list items
                    else:
                        items = spec_elem.find_all(['li', 'div'])
                        for item in items:
                            text = item.get_text(strip=True)
                            if ':' in text:
                                parts = text.split(':', 1)
                                if len(parts) == 2:
                                    key = parts[0].strip()
                                    value = parts[1].strip()
                                    if key and value:
                                        product_data['specifications'][key] = value
                    if product_data['specifications']:
                        break
            
            # Extract related parts - look for links containing part numbers (PS followed by digits)
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                # Look for part numbers in href or text
                part_match = re.search(r'PS\d+', href + ' ' + text)
                if part_match:
                    part_num = part_match.group(0)
                    if part_num not in product_data['related_parts'] and part_num != part_number:
                        product_data['related_parts'].append(part_num)
            
            # Fallback: if title is still empty, try to extract from page structure
            if not product_data.get('title'):
                # Try meta tags
                og_title = soup.find('meta', property='og:title')
                if og_title:
                    product_data['title'] = og_title.get('content', '')
                
                # Last resort: use part number
                if not product_data.get('title'):
                    product_data['title'] = f"Part {part_number}"
            
        except Exception as e:
            logger.error(f"Error extracting product data with BeautifulSoup: {e}")
            # Fallback
            product_data['title'] = f"Part {part_number}"
        
        return product_data
    
    async def _extract_model_data_with_bs4(self, html_content: str, model_number: str, url: str) -> Dict:
        """Use BeautifulSoup to extract structured model data from HTML."""
        data = {
            'model_number': model_number,
            'url': url,
            'title': '',
            'description': '',
            'instructions': '',
            'appliance_type': None,
            'compatible_parts': []
        }
        
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Extract title from h1 or page title
            title_elem = soup.find('h1')
            if title_elem:
                data['title'] = title_elem.get_text(strip=True)
            else:
                title_tag = soup.find('title')
                if title_tag:
                    data['title'] = title_tag.get_text(strip=True)
            
            # Extract description
            description_selectors = [
                '.model-description',
                '.description',
                '#description',
                '[class*="description"]',
                'meta[name="description"]'
            ]
            
            for selector in description_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    if desc_elem.name == 'meta':
                        data['description'] = desc_elem.get('content', '')
                    else:
                        data['description'] = desc_elem.get_text(strip=True)
                    if data['description']:
                        break
            
            # Extract instructions
            instruction_selectors = [
                '.instructions',
                '.installation-instructions',
                '.setup-instructions',
                '[class*="instruction"]',
                '[id*="instruction"]'
            ]
            
            for selector in instruction_selectors:
                instr_elem = soup.select_one(selector)
                if instr_elem:
                    data['instructions'] = instr_elem.get_text(strip=True)
                    if data['instructions']:
                        break
            
            # Determine appliance type
            text_to_check = (data.get('title', '') + ' ' + data.get('description', '')).lower()
            if 'refrigerator' in text_to_check or 'fridge' in text_to_check:
                data['appliance_type'] = 'refrigerator'
            elif 'dishwasher' in text_to_check:
                data['appliance_type'] = 'dishwasher'
            
            # Extract compatible parts - look for part links and part lists
            # First, try to find a parts list or compatible parts section
            parts_selectors = [
                '.compatible-parts',
                '.parts-list',
                '.related-parts',
                '[class*="part"]',
                '[id*="part"]'
            ]
            
            found_parts_section = False
            for selector in parts_selectors:
                parts_elem = soup.select_one(selector)
                if parts_elem:
                    # Look for links with part numbers
                    links = parts_elem.find_all('a', href=True)
                    for link in links:
                        href = link.get('href', '')
                        text = link.get_text(strip=True)
                        part_match = re.search(r'PS\d+', href + ' ' + text)
                        if part_match:
                            part_num = part_match.group(0)
                            part_desc = text if text else link.get('title', '')
                            # Check if we already have this part
                            if not any(p.get('part_number') == part_num for p in data['compatible_parts']):
                                data['compatible_parts'].append({
                                    'part_number': part_num,
                                    'description': part_desc
                                })
                    if data['compatible_parts']:
                        found_parts_section = True
                        break
            
            # Fallback: search all links on the page for part numbers
            if not found_parts_section:
                all_links = soup.find_all('a', href=True)
                for link in all_links:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    part_match = re.search(r'PS\d+', href + ' ' + text)
                    if part_match:
                        part_num = part_match.group(0)
                        part_desc = text if text else link.get('title', '')
                        # Check if we already have this part
                        if not any(p.get('part_number') == part_num for p in data['compatible_parts']):
                            data['compatible_parts'].append({
                                'part_number': part_num,
                                'description': part_desc
                            })
            
            # Fallback: if title is still empty
            if not data.get('title'):
                og_title = soup.find('meta', property='og:title')
                if og_title:
                    data['title'] = og_title.get('content', '')
                if not data.get('title'):
                    data['title'] = f"Model {model_number}"
            
        except Exception as e:
            logger.error(f"Error extracting model data with BeautifulSoup: {e}")
            # Fallback
            data['title'] = f"Model {model_number}"
        
        return data

    async def _scrape_product_page_from_playwright(self, url: str, part_number: str) -> Dict:
        """Scrape product information from the current page using BeautifulSoup."""
        try:
            # Wait for page to be fully loaded
            await asyncio.sleep(2)  # Give time for dynamic content to load
            
            # Wait for main content to be visible
            try:
                await self.page.wait_for_selector('body', state='visible', timeout=10000)
            except PlaywrightTimeoutError:
                logger.warning("Body element not found, continuing anyway...")
            
            # Get HTML content from the page
            html_content = await self.page.content()
            logger.info(f"Extracted {len(html_content)} characters of HTML from product page")
            
            if not html_content or len(html_content) < 100:
                logger.error(f"Failed to extract meaningful HTML from product page. URL: {url}")
                return {
                    'part_number': part_number,
                    'url': url,
                    'title': f'Part {part_number}',
                    'description': '',
                    'appliance_type': None,
                    'compatibility': [],
                    'installation_guide': '',
                    'specifications': {},
                    'related_parts': []
                }
            
            # Use BeautifulSoup to extract structured data
            product_data = await self._extract_product_data_with_bs4(html_content, part_number, url)
            
            return product_data
            
        except Exception as e:
            logger.error(f"Error scraping product page with Playwright: {e}")
            return {}
    
    async def scrape_product_page(self, part_number: str) -> Optional[Dict]:
        """Main method to scrape product page using Playwright."""
        return await self.search_and_get_product(part_number)
    
    async def scrape_model_page(self, model_number: str) -> Optional[Dict]:
        """
        Scrape model page for instructions and information using Playwright.
        
        Model URLs are typically: /Models/{model_number}/
        """
        await self._ensure_initialized()
        
        if not self.page:
            logger.warning("Playwright page not available")
            return None
        
        try:
            model_url = f"{self.base_url}/Models/{model_number}/"
            logger.info(f"Navigating to model page: {model_url}")
            
            try:
                await self.page.goto(model_url, wait_until='domcontentloaded', timeout=30000)
            except PlaywrightTimeoutError:
                logger.warning("Page load timeout for model page, continuing anyway...")
                # Stop loading
                await self.page.evaluate("window.stop()")
            await asyncio.sleep(2)
            
            # Wait for page to load
            try:
                await self.page.wait_for_selector('body', state='visible', timeout=10000)
            except PlaywrightTimeoutError:
                logger.warning("Body element not found")
            
            # Get HTML content from the page
            html_content = await self.page.content()
            logger.info(f"Extracted {len(html_content)} characters of HTML from model page")
            
            # Use BeautifulSoup to extract structured data
            data = await self._extract_model_data_with_bs4(html_content, model_number, model_url)
            
            # Process compatible parts to ensure correct format
            compatible_parts = []
            if data.get('compatible_parts'):
                for part in data['compatible_parts']:
                    if isinstance(part, dict):
                        compatible_parts.append(part)
                    elif isinstance(part, str):
                        # If it's a string, try to extract part number
                        part_match = re.search(r'PS\d+', part)
                        if part_match:
                            compatible_parts.append({
                                'part_number': part_match.group(0),
                                'description': part
                            })
            
            data['compatible_parts'] = compatible_parts
            
            return data
            
        except Exception as e:
            logger.error(f"Error scraping model page with Playwright: {e}")
            return {}

