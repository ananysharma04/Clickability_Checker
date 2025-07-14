import time      
import json     
from datetime import datetime
import hashlib 
import requests # type: ignore
from selenium import webdriver # type: ignore
from selenium.webdriver.common.by import By # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore
from selenium.webdriver.common.action_chains import ActionChains # type: ignore
from selenium.common.exceptions import ( # type: ignore
    TimeoutException, 
    ElementClickInterceptedException,
    StaleElementReferenceException,
    NoSuchElementException,
    WebDriverException
)
from selenium.webdriver.chrome.options import Options # type: ignore
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException # type: ignore

class ClickableElementTester:
    def __init__(self, headless=False, timeout=10):
        """
        Initialize the clickable element tester
        
        Args:
            headless (bool): Run browser in headless mode
            timeout (int): Default timeout for operations
        """
        self.timeout = timeout
        self.results = []
        self.driver = self._setup_driver(headless)
            
    def _setup_driver(self, headless):
        """Setup Chrome WebDriver with appropriate options"""
        chrome_options = Options()
        
        if headless:
            chrome_options.add_argument("--headless")
        
        # Additional options for better compatibility
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Set window size for consistent testing
        chrome_options.add_argument("--window-size=1920,1080")
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            print(f"Error setting up Chrome driver: {e}")
            print("Make sure ChromeDriver is installed and in PATH")
            raise

    def _handle_carousel_banner(self, element):
        """
        Handle auto-scrolling carousels and banners by pausing them and collecting all slides
        
        Args:
            element: WebElement that might be part of a carousel
            
        Returns:
            list: All clickable elements from carousel slides
        """
        carousel_elements = []
        
        try:
            # Find parent carousel container
            carousel_container = self.driver.execute_script("""
                var element = arguments[0];
                var current = element;
                var carouselSelectors = [
                    '.carousel', '.slider', '.banner-slider', '.swiper', '.slick',
                    '[data-ride="carousel"]', '.owl-carousel', '.hero-banner',
                    '.banner-container', '.slideshow', '.image-slider'
                ];
                
                while (current && current !== document.body) {
                    var className = current.className || '';
                    var dataRide = current.getAttribute('data-ride') || '';
                    
                    for (var i = 0; i < carouselSelectors.length; i++) {
                        var selector = carouselSelectors[i].replace('.', '');
                        if (className.includes(selector) || dataRide === 'carousel') {
                            return current;
                        }
                    }
                    current = current.parentElement;
                }
                return null;
            """, element)
            
            if carousel_container:
                print(f"Found carousel container, attempting to pause auto-scroll")
                
                # Pause carousel auto-scrolling
                self._pause_carousel(carousel_container)
                
                # Get all slides/banner items
                slides = self._get_all_carousel_slides(carousel_container)
                
                # Extract clickable elements from each slide
                for slide in slides:
                    slide_clickables = self._extract_clickables_from_slide(slide)
                    carousel_elements.extend(slide_clickables)
                    
            return carousel_elements
            
        except Exception as e:
            print(f"Error handling carousel: {e}")
            return []

    def _pause_carousel(self, carousel_container):
        """Pause carousel auto-scrolling using various methods"""
        try:
            # Method 1: Bootstrap carousel pause
            self.driver.execute_script("""
                var carousel = arguments[0];
                if (typeof jQuery !== 'undefined' && jQuery(carousel).carousel) {
                    jQuery(carousel).carousel('pause');
                }
                if (carousel.carousel && typeof carousel.carousel === 'function') {
                    carousel.carousel('pause');
                }
            """, carousel_container)
            
            # Method 2: Pause CSS animations
            self.driver.execute_script("""
                var carousel = arguments[0];
                carousel.style.animationPlayState = 'paused';
                carousel.style.webkitAnimationPlayState = 'paused';
                
                // Pause all child animations
                var children = carousel.querySelectorAll('*');
                for (var i = 0; i < children.length; i++) {
                    children[i].style.animationPlayState = 'paused';
                    children[i].style.webkitAnimationPlayState = 'paused';
                }
            """, carousel_container)
            
            # Method 3: Clear intervals (common for custom sliders)
            self.driver.execute_script("""
                // Clear common slider intervals
                if (window.sliderIntervals) {
                    window.sliderIntervals.forEach(clearInterval);
                }
                
                // Stop common slider libraries
                var carousel = arguments[0];
                if (carousel.swiper) {
                    carousel.swiper.autoplay.stop();
                }
                if (carousel.slick) {
                    jQuery(carousel).slick('slickPause');
                }
            """, carousel_container)
            
            time.sleep(1)  # Allow pause to take effect
            
        except Exception as e:
            print(f"Could not pause carousel: {e}")

    def _get_all_carousel_slides(self, carousel_container):
        """Get all slides from a carousel, including hidden ones"""
        slides = []
        
        try:
            # Common slide selectors
            slide_selectors = [
                '.carousel-item', '.slide', '.slider-item', '.swiper-slide',
                '.slick-slide', '.banner-slide', '.owl-item', '[data-slide]',
                '.glide__slide', '.splide__slide', '.flickity-cell',
                '.keen-slider__slide', '.embla__slide', '.tns-item',
                '.carousel-cell', '.slider-slide', '.slide-item',
                # Generic selectors for custom implementations
                '[class*="slide"]', '[data-slide-index]', '[data-slide-id]'
            ]
            
            for selector in slide_selectors:
                found_slides = carousel_container.find_elements(By.CSS_SELECTOR, selector)
                if found_slides:
                    slides.extend(found_slides)
                    break
            
            # If no specific slides found, look for direct children with images/content
            if not slides:
                potential_slides = carousel_container.find_elements(By.CSS_SELECTOR, 'div, section, article, li')
                slides = [slide for slide in potential_slides if self._looks_like_slide(slide)]

            if not slides:
                nested_containers = carousel_container.find_elements(By.CSS_SELECTOR, 
                    '.swiper-wrapper, .slider-wrapper, .carousel-inner, .slides')
                for container in nested_containers:
                    nested_slides = container.find_elements(By.CSS_SELECTOR, 'div, li')
                    for slide in nested_slides:
                        if self._looks_like_slide(slide):
                            slides.append(slide)
            
            print(f"Found {len(slides)} carousel slides")
            return slides
            
        except Exception as e:
            print(f"Error getting carousel slides: {e}")
            return []

    def _looks_like_slide(self, element):
        """Check if an element looks like a carousel slide"""
        try:
            # Check for typical slide content
            has_image = len(element.find_elements(By.TAG_NAME, 'img')) > 0
            has_text_content = len(element.text.strip()) > 20
            has_links = len(element.find_elements(By.TAG_NAME, 'a')) > 0
            
            # return has_image or has_text_content or has_links
            has_buttons = len(element.find_elements(By.TAG_NAME, 'button')) > 0
        
            # Check for slide-like styling
            style = element.get_attribute('style') or ''
            computed_style = self.driver.execute_script("""
                var element = arguments[0];
                var style = window.getComputedStyle(element);
                return {
                    display: style.display,
                    position: style.position,
                    width: style.width,
                    float: style.float,
                    flexBasis: style.flexBasis
                };
            """, element)
            
            # Check if element has slide-like dimensions or positioning
            has_slide_styling = (
                'width:' in style.lower() or 
                computed_style.get('position') in ['absolute', 'relative'] or
                computed_style.get('float') in ['left', 'right'] or
                computed_style.get('display') in ['flex', 'inline-block']
            )
            
            # Check class names for slide indicators
            class_names = element.get_attribute('class') or ''
            has_slide_class = any(keyword in class_names.lower() for keyword in 
                                ['slide', 'item', 'cell', 'panel', 'tab'])
            
            return (has_image or has_text_content or has_links or has_buttons or 
                    has_slide_styling or has_slide_class)
        except:
            return False

    def _extract_clickables_from_slide(self, slide):
        """Extract clickable elements from a single slide"""
        clickables = []
        
        try:
            # Make slide visible if hidden
            self.driver.execute_script("""
                var slide = arguments[0];
                var originalDisplay = slide.style.display;
                var originalVisibility = slide.style.visibility;
                var originalOpacity = slide.style.opacity;
                var originalTransform = slide.style.transform;
                var originalPosition = slide.style.position;
                
                slide.style.display = 'block';
                slide.style.visibility = 'visible';
                slide.style.opacity = '1';
                slide.style.transform = 'translateX(0px)';
                slide.style.position = 'relative';
                slide.style.zIndex = '1000';
                
                // Store original values for restoration
                slide.setAttribute('data-original-display', originalDisplay);
                slide.setAttribute('data-original-visibility', originalVisibility);
                slide.setAttribute('data-original-opacity', originalOpacity);
                slide.setAttribute('data-original-transform', originalTransform);
                slide.setAttribute('data-original-position', originalPosition);
            """, slide)
            
            time.sleep(1)

            # Find clickable elements in this slide
            clickable_selectors = [
                'a', 'button', '[onclick]', '[role="button"]','input[type="button"]',
                'input[type="submit"]', '.btn', '.button', '.link', '.cta', '.call-to-action',
                '[data-action]', '[data-click]', '[data-href]',
                '.carousel-control', '.slider-nav', '.slide-nav',
                '.prev', '.next', '.slide-btn', '.carousel-btn',

            ]
            for selector in clickable_selectors:
                try:
                    elements = slide.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_enabled():  # Don't check is_displayed() as slide might be hidden
                            element_info = self._extract_element_info_for_hidden(element)
                            if element_info:
                                clickables.append(element_info)
                except Exception as e:
                    print(f"Error finding elements with selector '{selector}': {e}")

            # Additionally, find elements by common action words in their text (XPath)
            action_words = [
                'WATCH VIDEO', 'PLAY', 'SUBMIT', 'APPLY', 'START', 'LEARN MORE', 'READ MORE',
                'VIEW', 'SEE MORE', 'CLICK HERE', 'DOWNLOAD', 'UPLOAD', 'NEXT', 'PREV', 'PREVIOUS'
            ]
            for word in action_words:
                try:
                    xpath = f".//*[contains(translate(text(), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{word}')]"
                    elements = slide.find_elements(By.XPATH, xpath)
                    for element in elements:
                        if element.is_enabled():
                            element_info = self._extract_element_info_for_hidden(element)
                            if element_info:
                                clickables.append(element_info)
                except Exception as e:
                    print(f"Error finding elements with text '{word}': {e}")

        except Exception as e:
            print(f"Error extracting clickables from slide: {e}")

        return clickables
    def _extract_element_info_for_hidden(self, element):
        """Extract element info even if element is not currently displayed"""
        try:
            # Temporarily make element visible for info extraction
            original_style = self.driver.execute_script("""
                var el = arguments[0];
                var style = {
                    display: el.style.display,
                    visibility: el.style.visibility,
                    opacity: el.style.opacity
                };
                el.style.display = 'block';
                el.style.visibility = 'visible';
                el.style.opacity = '1';
                return style;
            """, element)
            
            element_info = {
                'tag_name': element.tag_name,
                'text': element.text.strip()[:100] if element.text else '',
                'class_names': element.get_attribute('class') or '',
                'id': element.get_attribute('id') or '',
                'href': element.get_attribute('href') or '',
                'status_code': self.get_status_code(href) if href else None, # type: ignore
                'onclick': element.get_attribute('onclick') or '',
                'role': element.get_attribute('role') or '',
                'type': element.get_attribute('type') or '',
                'data_testid': element.get_attribute('data-testid') or '',
                'aria_label': element.get_attribute('aria-label') or '',
                'xpath': self._get_element_xpath(element),
                'location': element.location,
                'size': element.size,
                'is_displayed': True,  # We're forcing it to be displayed
                'is_enabled': element.is_enabled(),
                'is_carousel_element': True  # Mark as carousel element
            }
            
            # Restore original styles
            self.driver.execute_script("""
                var el = arguments[0];
                var style = arguments[1];
                el.style.display = style.display;
                el.style.visibility = style.visibility;
                el.style.opacity = style.opacity;
            """, element, original_style)
            
            element_info['unique_id'] = self._create_unique_id(element_info)
            return element_info
            
        except Exception as e:
            print(f"Error extracting hidden element info: {e}")
            return None

    def _is_duplicate_element(self, element_info, existing_elements):
        """Check for duplicate elements more accurately"""
        for existing in existing_elements:
            if (existing['xpath'] == element_info['xpath'] or
                (existing['unique_id'] == element_info['unique_id'] and
                existing['tag_name'] == element_info['tag_name'] and
                existing['text'] == element_info['text'])):
                return True
        return False

    def find_clickable_elements(self, url):
    #    """
    #     Find all potentially clickable elements on the page
        
    #     Args:
    #         url (str): URL to test
            
    #     Returns:
    #         list: List of clickable elements with their properties
    #     """
        self.url = url
        print(f"Loading URL: {url}")
        self.driver.get(url)
        
        # Wait for page to load
        try:
            WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            print("⚠️ Page load timeout - proceeding with available elements")
        
        # Allow additional time for dynamic content
        time.sleep(5)

        # Define header and footer exclusion selectors
        header_footer_selectors = [
            'header', 'nav', 'footer',
            '.header', '.nav', '.footer', '.navigation',
            '#header', '#nav', '#footer', '#navigation',
            '[role="banner"]', '[role="navigation"]', '[role="contentinfo"]',
            '.site-header', '.site-footer', '.page-header', '.page-footer',
            '.main-header', '.main-footer', '.top-nav', '.bottom-nav',
            '.navbar', '.nav-bar', '.site-nav', '.primary-nav'
        ]
        
        # Get main content area (exclude header/footer)
        main_content_area = self._get_main_content_area()

        # First, identify and handle carousels/banners
        carousel_elements = []
        carousel_selectors = [
            '.carousel', '.slider', '.banner-slider', '.swiper', '.slick',
            '[data-ride="carousel"]', '.owl-carousel', '.hero-banner',
            '.banner-container', '.slideshow', '.image-slider',
            '.swiper-container', '.swiper-wrapper', '.glide', '.splide',
            '.flickity', '.keen-slider', '.embla', '.tiny-slider',
            '[data-carousel]', '[data-slider]', '[data-swiper]',
            '.slide-container', '.carousel-container', '.slider-wrapper',
            '.hero-slider', '.product-slider', '.testimonial-slider',
            '.gallery-slider', '.content-slider', '.banner-carousel',
            '.thumbnail__overlay'  # Added thumbnail overlay to carousel selectors
        ]
        
        unique_ids = set()
        clickable_elements = []
        
        for carousel_selector in carousel_selectors:
            try:
                if main_content_area:
                    carousels = main_content_area.find_elements(By.CSS_SELECTOR, carousel_selector)
                else:
                    carousels = self.driver.find_elements(By.CSS_SELECTOR, carousel_selector)
                    
                for carousel in carousels:
                    try:
                        if carousel.is_displayed():
                            # Skip if carousel is in header/footer
                            if self._is_in_header_or_footer(carousel, header_footer_selectors):
                                continue
                            
                            print(f"Processing carousel with selector: {carousel_selector}")
                            carousel_clickables = self._handle_carousel_banner(carousel)
                            carousel_elements.extend(carousel_clickables)
                    except StaleElementReferenceException:
                        continue
                    except Exception as e:
                        print(f"Error processing carousel element: {e}")
                        continue
            except Exception as e:
                print(f"Error processing carousel selector '{carousel_selector}': {e}")
        
        # CSS selectors for potentially clickable elements
        clickable_selectors = [
            # Basic clickable elements
            'a', 'button', 
            'input[type="button"]', 'input[type="submit"]', 'input[type="reset"]',
            
            # Elements with interactive attributes
            '[onclick]', '[onmousedown]', '[onmouseup]', '[ondblclick]',
            
            # ARIA roles
            '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
            '[role="option"]', '[role="treeitem"]', '[role="gridcell"]',
            
            # Focusable elements (potential clickables)
            '[tabindex="0"]', '[tabindex="-1"]', 'div[tabindex]', 'span[tabindex]',
            'li[tabindex]', 'td[tabindex]', 'th[tabindex]',
            
            # Common clickable classes and patterns
            '.btn', '.button', '.link', '.clickable', '.click',
            '.cta', '.call-to-action', '.action', '.trigger',
            '.menu-item', '.nav-item', '.tab', '.accordion',
            '.dropdown', '.select', '.picker', '.toggle',
            '.card', '.tile', '.item', '.option',
            '.close', '.cancel', '.submit', '.save', '.edit', '.delete',
            '.expand', '.collapse', '.show', '.hide',
            '.play', '.pause', '.stop', '.next', '.prev', '.previous',
            '.like', '.share', '.favorite', '.bookmark',
            '.download', '.upload', '.search', '.filter', '.sort',
            
            # Data attributes (modern web patterns)
            '[data-action]', '[data-click]', '[data-href]', '[data-url]',
            '[data-toggle]', '[data-target]', '[data-dismiss]',
            '[data-testid*="button"]', '[data-testid*="link"]', '[data-testid*="click"]',
            '[data-cy*="button"]', '[data-cy*="link"]', '[data-cy*="click"]',
            
            # Form controls that might be styled as buttons
            'select', 'input[type="checkbox"]', 'input[type="radio"]',
            'input[type="file"]', 'input[type="image"]',
            
            # Modern web components and custom elements
            '[class*="btn"]', '[class*="button"]', '[class*="link"]',
            '[class*="click"]', '[class*="action"]', '[class*="cta"]',
            '[id*="btn"]', '[id*="button"]', '[id*="link"]','[class="calculator-button active"]'
            # class="calculator-button active"
            
            # Media controls
            'video[controls]', 'audio[controls]',
            
            # Interactive list items and table cells
            'li[onclick]', 'td[onclick]', 'tr[onclick]',
            'li[role="button"]', 'td[role="button"]', 'tr[role="button"]',
            
            # SVG elements that might be clickable
            'svg[onclick]', 'svg[role="button"]',
            
            # Image maps and clickable images
            'area', 'img[onclick]', 'img[role="button"]',
            
            # Custom interactive elements
            'div[role="button"]', 'span[role="button"]',
            'p[role="button"]', 'section[role="button"]',
            
            # Thumbnail overlay specifically
            '.thumbnail__overlay'
        ]

        for selector in clickable_selectors:
            try:
                if main_content_area:
                    # Search within main content area only
                    elements = main_content_area.find_elements(By.CSS_SELECTOR, selector)
                else:
                    # Fallback: search entire page but exclude header/footer elements
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                
                for element in elements:
                    try:
                        # Check if element is displayed and enabled
                        if element.is_displayed() and element.is_enabled():
                            # Skip if element is within header or footer
                            if self._is_in_header_or_footer(element, header_footer_selectors):
                                continue

                            # Skip if element is already captured as part of carousel
                            if self._is_carousel_element(element):
                                continue
                                
                            element_info = self._extract_element_info(element)
                            if element_info and element_info['unique_id'] not in unique_ids:
                                unique_ids.add(element_info['unique_id'])
                                clickable_elements.append(element_info)
                    except StaleElementReferenceException:
                        continue
                    except Exception as e:
                        print(f"Error processing element: {e}")
                        continue
            except Exception as e:
                print(f"Error finding elements with selector '{selector}': {e}")
                continue
        
        # Find elements with pointer cursor
        try:
            pointer_elements = self._find_elements_with_pointer_cursor()
            for element in pointer_elements:
                try:
                    if element.is_displayed() and element.is_enabled():
                        if self._is_in_header_or_footer(element, header_footer_selectors):
                            continue
                            
                        if self._is_carousel_element(element):
                            continue
                            
                        element_info = self._extract_element_info(element)
                        if element_info and element_info['unique_id'] not in unique_ids:
                            unique_ids.add(element_info['unique_id'])
                            element_info['detection_method'] = 'pointer_cursor'
                            clickable_elements.append(element_info)
                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue
        except Exception as e:
            print(f"Error finding pointer cursor elements: {e}")

        # Find elements with event listeners
        try:
            listener_elements = self._find_elements_with_event_listeners()
            for element in listener_elements:
                try:
                    if element.is_displayed() and element.is_enabled():
                        if self._is_in_header_or_footer(element, header_footer_selectors):
                            continue
                            
                        if self._is_carousel_element(element):
                            continue
                            
                        element_info = self._extract_element_info(element)
                        if element_info and element_info['unique_id'] not in unique_ids:
                            unique_ids.add(element_info['unique_id'])
                            element_info['detection_method'] = 'event_listener'
                            clickable_elements.append(element_info)
                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue
        except Exception as e:
            print(f"Error finding event listener elements: {e}")

        clickable_elements.extend(carousel_elements)
        print(f"Found {len(clickable_elements)} potentially clickable elements (excluding header/footer)")
        return clickable_elements
    def safe_get_attribute(self, element, attribute, default=''):
            """Safely get element attribute with error handling"""
            try:
                return element.get_attribute(attribute) or default
            except Exception:
                return default

    def safe_get_text(self, element):
        """Safely get element text with error handling"""
        try:
            return element.text.strip()
        except Exception:
            return ''
  
    
    def _find_elements_with_pointer_cursor(self):
        """Find elements that have cursor: pointer styling (likely clickable)"""
        try:
            pointer_elements = self.driver.execute_script("""
                var elements = [];
                var allElements = document.querySelectorAll('*');
                
                for (var i = 0; i < allElements.length; i++) {
                    var element = allElements[i];
                    var computedStyle = window.getComputedStyle(element);
                    
                    if (computedStyle.cursor === 'pointer' && 
                        element.offsetWidth > 0 && element.offsetHeight > 0) {
                        elements.push(element);
                    }
                }
                
                return elements;
            """)
            
            print(f"Found {len(pointer_elements)} elements with pointer cursor")
            return pointer_elements
        except Exception as e:
            print(f"Error finding pointer cursor elements: {e}")
            return []

    def _find_elements_with_event_listeners(self):
        """Find elements that have click event listeners attached"""
        try:
            listener_elements = self.driver.execute_script("""
                var elements = [];
                var allElements = document.querySelectorAll('*');
                
                for (var i = 0; i < allElements.length; i++) {
                    var element = allElements[i];
                    
                    // Check for common event listener patterns
                    if (element.onclick || 
                        element.onmousedown || 
                        element.onmouseup ||
                        element.getAttribute('onclick') ||
                        element.hasAttribute('data-action') ||
                        element.hasAttribute('data-click') ||
                        element.hasAttribute('data-href')) {
                        
                        if (element.offsetWidth > 0 && element.offsetHeight > 0) {
                            elements.push(element);
                        }
                    }
                }
                
                return elements;
            """)
            
            print(f"Found {len(listener_elements)} elements with event listeners")
            return listener_elements
        except Exception as e:
            print(f"Error finding event listener elements: {e}")
            return []

    def _get_main_content_area(self):
        """
        Identify and return the main content area of the page
        
        Returns:
            WebElement: Main content area element or None
        """
        # Common selectors for main content areas
        main_content_selectors = [
            'main',
            '[role="main"]',
            '#main',
            '#content',
            '#main-content',
            '.main-content',
            '.content',
            '.page-content',
            '.site-content'
        ]
        
        for selector in main_content_selectors:
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed():
                    print(f"Found main content area using selector: {selector}")
                    return element
            except NoSuchElementException:
                continue
            except Exception as e:
                print(f"Error checking selector '{selector}': {e}")
                continue
        
        print("No specific main content area found, will use exclusion method")
        return None
    
    def _is_in_header_or_footer(self, element, header_footer_selectors):
        """
        Check if an element is within header or footer sections
        
        Args:
            element: WebElement to check
            header_footer_selectors: List of CSS selectors for header/footer elements
            
        Returns:
            bool: True if element is in header or footer
        """
        try:
            # Check if element itself is a header/footer
            element_tag = element.tag_name.lower()
            if element_tag in ['header', 'nav', 'footer']:
                return True
            
            # Check element classes and IDs
            element_class = element.get_attribute('class') or ''
            element_id = element.get_attribute('id') or ''
            element_role = element.get_attribute('role') or ''
            
            # Check for header/footer indicators in class or ID
            header_footer_keywords = [
                'header', 'nav', 'navigation', 'navbar', 'nav-bar', 'footer',
                'site-header', 'site-footer', 'page-header', 'page-footer',
                'main-header', 'main-footer', 'top-nav', 'bottom-nav',
                'primary-nav', 'secondary-nav', 'breadcrumb'
            ]
            
            element_attributes = f"{element_class} {element_id}".lower()
            for keyword in header_footer_keywords:
                if keyword in element_attributes:
                    return True
            
            # Check ARIA roles
            if element_role in ['banner', 'navigation', 'contentinfo']:
                return True
            
            # Check if element is within a header/footer parent
            try:
                # Use JavaScript to check if element is within header/footer
                is_in_header_footer = self.driver.execute_script("""
                    var element = arguments[0];
                    var current = element;
                    
                    while (current && current !== document.body) {
                        var tagName = current.tagName ? current.tagName.toLowerCase() : '';
                        var className = current.className || '';
                        var id = current.id || '';
                        var role = current.getAttribute('role') || '';
                        
                        // Check tag names
                        if (['header', 'nav', 'footer'].includes(tagName)) {
                            return true;
                        }
                        
                        // Check roles
                        if (['banner', 'navigation', 'contentinfo'].includes(role)) {
                            return true;
                        }
                        
                        // Check class names and IDs
                        var attributes = (className + ' ' + id).toLowerCase();
                        var keywords = ['header', 'nav', 'navigation', 'navbar', 'nav-belt', 
                                       'footer', 'navfooter', 'site-header', 'site-footer',
                                       'page-header', 'page-footer', 'main-header', 'main-footer'];
                        
                        for (var i = 0; i < keywords.length; i++) {
                            if (attributes.includes(keywords[i])) {
                                return true;
                            }
                        }
                        
                        current = current.parentElement;
                    }
                    
                    return false;
                """, element)
                
                return is_in_header_footer
                
            except Exception as e:
                print(f"Error checking parent elements: {e}")
                return False
                
        except Exception as e:
            print(f"Error checking if element is in header/footer: {e}")
            return False
    
    def _is_carousel_element(self, element):
        """Check if element is part of a carousel that we've already processed"""
        try:
            return self.driver.execute_script("""
                var element = arguments[0];
                var current = element;
                var carouselSelectors = [
                    'carousel', 'slider', 'banner-slider', 'swiper', 'slick',
                    'owl-carousel', 'hero-banner', 'banner-container', 'slideshow'
                ];
                
                while (current && current !== document.body) {
                    var className = current.className || '';
                    for (var i = 0; i < carouselSelectors.length; i++) {
                        if (className.includes(carouselSelectors[i])) {
                            return true;
                        }
                    }
                    current = current.parentElement;
                }
                return false;
            """, element)
        except:
            return False

    def _get_element_css_selector(self, element):
            """Generate a CSS selector for the element"""
            try:
                return self.driver.execute_script("""
                    function getCssSelector(el) {
                        if (!(el instanceof Element)) return '';
                        var path = [];
                        while (el.nodeType === Node.ELEMENT_NODE) {
                            var selector = el.nodeName.toLowerCase();
                            if (el.id) {
                                selector += '#' + el.id;
                                path.unshift(selector);
                                break;
                            } else {
                                var sib = el, nth = 1;
                                while (sib = sib.previousElementSibling) {
                                    if (sib.nodeName.toLowerCase() == selector)
                                        nth++;
                                }
                                if (nth != 1)
                                    selector += ":nth-of-type(" + nth + ")";
                            }
                            path.unshift(selector);
                            el = el.parentNode;
                        }
                        return path.join(" > ");
                    }
                    return getCssSelector(arguments[0]);
                """, element)
            except Exception:
                return "css_selector_unavailable"

    def get_status_code(self, href):
        """Return HTTP status code for the given href, or None if not applicable."""
        try:
            if not href or href.startswith('#') or href.startswith('javascript:'):
                return None
            # Handle relative URLs
            if href.startswith('/'):
                from urllib.parse import urljoin
                href = urljoin(self.url, href)
            response = requests.head(href, allow_redirects=True, timeout=5)
            status_chain = [r.status_code for r in response.history] + [response.status_code]
            return status_chain  # Return final status code
            # return response.status_code
        except Exception:
            return None
        
    def _extract_element_info(self, element):
        """
        Extract and deduplicate element info based on unique content signature.
        """
        try:
            # Skip hidden/invisible elements
            # if not element.is_displayed():
            #     return None

            # Extract key info
            tag_name = element.tag_name
            text = element.text.strip()[:100] if element.text else ''
            class_names = element.get_attribute('class') or ''
            href = element.get_attribute('href') or ''
            status_code = self.get_status_code(href) if href else None, 
            onclick = element.get_attribute('onclick') or ''
            element_id = element.get_attribute('id') or ''

            # Create deduplication hash (more robust and minimalistic)
            dedup_key = f"{tag_name}|{text}|{href}|{class_names}|{element_id}"
            unique_id = hashlib.md5(dedup_key.encode()).hexdigest()

            # Deduplication set
            if not hasattr(self, 'seen_elements'):
                self.seen_elements = set()
            if unique_id in self.seen_elements:
                return None  # Already processed
            self.seen_elements.add(unique_id)

            # Final full element info
            element_info = {
                'tag_name': tag_name,
                'text': text,
                'class_names': class_names,
                'id': element_id,
                'href': href,
                'onclick': onclick,
                'status_code': status_code,  # type: ignore
                'role': element.get_attribute('role') or '',
                'type': element.get_attribute('type') or '',
                'data_testid': element.get_attribute('data-testid') or '',
                'aria_label': element.get_attribute('aria-label') or '',
                'title': element.get_attribute('title') or '',
                'name': element.get_attribute('name') or '',
                'value': element.get_attribute('value') or '',
                'src': element.get_attribute('src') or '',
                'alt': element.get_attribute('alt') or '',
                'xpath': self._get_element_xpath(element),
                'css_selector': self._get_element_css_selector(element),
                'location': element.location,
                'size': element.size,
                'is_displayed': element.is_displayed(),
                'is_enabled': element.is_enabled(),
                'unique_id': unique_id
            }

            return element_info

        except Exception as e:
            print(f"Error extracting element info: {e}")
            return None
        
    def _get_element_xpath(self, element):
        """Generate XPath for an element"""
        try:
            return self.driver.execute_script(
                "function getXPath(element) {"
                "if (element.id !== '') return '//*[@id=\"' + element.id + '\"]';"
                "if (element === document.body) return '/html/body';"
                "var ix = 0;"
                "var siblings = element.parentNode.childNodes;"
                "for (var i = 0; i < siblings.length; i++) {"
                "var sibling = siblings[i];"
                "if (sibling === element) return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';"
                "if (sibling.nodeType === 1 && sibling.tagName === element.tagName) ix++;"
                "}"
                "}"
                "return getXPath(arguments[0]);", element
            )
        except:
            return "xpath_unavailable"
    
    def _create_unique_id(self, element_info):
        """Create a unique identifier for an element"""
        components = [
            element_info['tag_name'],
            element_info['id'],
            element_info['class_names'],
            element_info['text'][:50],
            str(element_info['location']),
        ]
        return hash('|'.join(str(c) for c in components))
    
    # def is_dead_click_by_href(self, element_info):
    #     """ Returns True if the element is a dead click based on href and onclick.
    #     """
    #     href = (element_info.get('href') or '').replace(' ', '').lower()
    #     onclick = (element_info.get('onclick') or '').strip()
    #     # Consider as dead click if href is javascript:void(0) or javascript::void(0) and no onclick
    #     return href in ['javascript:void(0)', 'javascript::void(0)'] and not onclick
    
    def is_dead_click_by_href(self, element_info):
                        """Returns True if the element is a dead click based on href."""
                        href = (element_info.get('href') or '').replace(' ', '').lower()
                        return href in ['javascript:void(0)', 'javascript::void(0)','#',' ']
    
    def test_element_click(self, element_info):
        """
        Test if an element click is functional or dead - with carousel support
        
        Args:
            element_info (dict): Element information
            
        Returns:
            dict: Test result
        """
        result = {
            'element_info': element_info,
            'click_status': 'unknown',
            'error_message': '',
            'page_changed': False,
            'url_before': '',
            'url_after': '',
            'new_elements_appeared': False,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            
            # Store initial state
            initial_url = self.driver.current_url
            initial_title = self.driver.title
            result['url_before'] = initial_url
            
            # Try to find the element again (to avoid stale references)
            # Special handling for carousel elements
            if element_info.get('is_carousel_element', False):
                element = self._find_and_prepare_carousel_element(element_info)
            else:
                element = self._find_element_by_info(element_info)
            
            if not element:
                result['click_status'] = 'element_not_found'
                result['error_message'] = 'Element could not be located for clicking'
                return result
            
            
            # For carousel elements, ensure they're visible before clicking
            if element_info.get('is_carousel_element', False):
                self._make_carousel_element_clickable(element)
            
            # Scroll element into view
            # self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            # time.sleep(0.5)
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(1)
            
            # Check if element is still clickable
            if not (element.is_displayed() and element.is_enabled()):
                result['click_status'] = 'not_clickable'
                result['error_message'] = 'Element is not displayed or enabled'
                return result
            
            # Attempt to click the element
            try:
                # Try regular click first
                element.click()
                click_successful = True
            except ElementClickInterceptedException:
                try:
                    # Try JavaScript click if regular click fails
                    self.driver.execute_script("arguments[0].click();", element)
                    click_successful = True
                except Exception as js_error:
                    result['click_status'] = 'click_intercepted'
                    result['error_message'] = f'Click intercepted: {str(js_error)}'
                    return result
            
            # Wait a moment for any changes to occur
            time.sleep(2)
            
            # Check for changes after click
            current_url = self.driver.current_url
            current_title = self.driver.title
            result['url_after'] = current_url
            
            # Determine if click was active or dead
            
            if self.is_dead_click_by_href(element_info):
                result['click_status'] = 'dead_click'
                result['error_message'] = 'Dead click: href is javascript:void(0)'
            elif current_url != initial_url:
                result['click_status'] = 'active_navigation'
                result['page_changed'] = True
            elif current_title != initial_title:
                result['click_status'] = 'active_title_change'
                result['page_changed'] = True
            else:
                # Check for new elements or modals
                try:
                    # Look for common indicators of dynamic content
                    modals = self.driver.find_elements(By.CSS_SELECTOR, 
                        '.modal, .popup, .overlay, .dialog, [role="dialog"], [role="alertdialog"]')
                    
                    dropdowns = self.driver.find_elements(By.CSS_SELECTOR,
                        '.dropdown-menu, .menu-open, [aria-expanded="true"]')
                    
                    if modals or dropdowns:
                        result['click_status'] = 'active_ui_change'
                        result['new_elements_appeared'] = True
                    else:
                        result['click_status'] = 'dead_click'
                        
                except Exception:
                    result['click_status'] = 'dead_click'
            
        except TimeoutException:
            result['click_status'] = 'timeout'
            result['error_message'] = 'Timeout waiting for element or page response'
        except StaleElementReferenceException:
            result['click_status'] = 'stale_element'
            result['error_message'] = 'Element became stale during test'
        except Exception as e:
            result['click_status'] = 'error'
            result['error_message'] = str(e)
        
        return result

    def _find_and_prepare_carousel_element(self, element_info):
        """Find carousel element and make it ready for clicking"""
        try:
            # First find the carousel container
            # carousel_list = [
            #     '.carousel', '.slider', '.banner-slider',
            #     '.swiper', '.slick', '[data-ride="carousel"]',
            #     '.owl-carousel', '.swiper-container', '.glide', '.splide', '.flickity',
            #     '[class*="carousel"], [class*="slider"], [class*="swiper"]'
            # ]
            carousel_containers = self.driver.find_elements(By.CSS_SELECTOR, 
                '.carousel, .slider, .banner-slider, .swiper, .slick, [data-ride="carousel"], ' +
                '.owl-carousel, .swiper-container, .glide, .splide, .flickity, ' +
                '[class*="carousel"], [class*="slider"], [class*="swiper"]'
            )
            
            for container in carousel_containers:
                # Pause the carousel
                self._pause_carousel(container)
                
                # Try to find the element within this carousel
                element = self._find_element_by_info_in_container(element_info, container)
                if element:
                    return element
            
            return None
            
        except Exception as e:
            print(f"Error finding carousel element: {e}")
            return None

    def _find_element_by_info_in_container(self, element_info, container):
        """Find element within a specific container"""
        strategies = [
            (By.ID, element_info['id']) if element_info['id'] else None,
            (By.XPATH, element_info['xpath']) if element_info['xpath'] != 'xpath_unavailable' else None,
            (By.CSS_SELECTOR, f".{element_info['class_names'].replace(' ', '.')}") if element_info['class_names'] else None,
        ]
        
        for strategy in strategies:
            if strategy:
                try:
                    elements = container.find_elements(*strategy)
                    for element in elements:
                        if (element.tag_name == element_info['tag_name'] and
                            element.text.strip()[:100] == element_info['text']):
                            return element
                except Exception:
                    continue
        
        return None

    def _make_carousel_element_clickable(self, element):
        """Make a carousel element visible and clickable"""
        try:
            # Make element and its parents visible
            self.driver.execute_script("""
                var element = arguments[0];
                var current = element;
                
                while (current && current !== document.body) {
                    current.style.display = 'block';
                    current.style.visibility = 'visible';
                    current.style.opacity = '1';
                    current.style.position = 'relative';
                    current.style.zIndex = 'auto';
                    
                    // Remove transforms that might hide the element
                    current.style.transform = 'none';
                    current.style.webkitTransform = 'none';
                    
                    current = current.parentElement;
                }
            """, element)
            
            time.sleep(0.5)  # Allow styles to apply
            
        except Exception as e:
            print(f"Error making carousel element clickable: {e}")


    
    
    def _find_element_by_info(self, element_info):
        """Find element using stored information"""
        strategies = [
            (By.ID, element_info['id']) if element_info['id'] else None,
            (By.XPATH, element_info['xpath']) if element_info['xpath'] != 'xpath_unavailable' else None,
            (By.CSS_SELECTOR, f".{element_info['class_names'].replace(' ', '.')}") if element_info['class_names'] else None,
        ]
        
        for strategy in strategies:
            if strategy:
                try:
                    elements = self.driver.find_elements(*strategy)
                    for element in elements:
                        if (element.is_displayed() and 
                            element.tag_name == element_info['tag_name'] and
                            element.text.strip()[:100] == element_info['text']):
                            return element
                except Exception:
                    continue
        
        return None
    
#   from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException

    # def close_popups(self):
    #     """Try to close common popups/modals if present."""
    #     popup_selectors = [
    #         # Add more selectors as needed for your site
    #         '[class*="close"]',         # Buttons with 'close' in class
    #         '[class*="Close"]',
    #         '[class*="popup-close"]',
    #         '[class*="modal-close"]',
    #         '[class*="close-btn"]',
    #         '[class*="close-button"]',
    #         '[aria-label="Close"]',
    #         '[data-dismiss="modal"]',
    #         '.mfp-close',               # Magnific Popup
    #         '.fancybox-close',          # Fancybox
    #         '.modal-footer .btn-close',
    #         '.modal-header .btn-close',
    #         '.modal .btn-close',
    #         '.modal .close',
    #         '.popup .close',
    #         '.popup-close',
    #         '.close-modal',
    #         '.close-btn',
    #         '.close-button',
    #         '.newsletter-popup__close',
    #         '.cookie-close',
    #         '.cookie-consent-close',
    #         '.cc-dismiss'
    #     ]
    #     for selector in popup_selectors:
    #         try:
    #             close_btns = self.driver.find_elements("css selector", selector)
    #             for btn in close_btns:
    #                 if btn.is_displayed() and btn.is_enabled():
    #                     btn.click()
    #                     print(f"Closed popup with selector: {selector}")
    #                     # Optionally, wait a bit for popup to disappear
    #                     import time
    #                     time.sleep(1)
    #         except (NoSuchElementException, ElementNotInteractableException):
    #             continue
 
 
    def run_comprehensive_test(self, url, max_elements=50):
        """
        Run comprehensive test on all clickable elements
        
        Args:
            url (str): URL to test
            max_elements (int): Maximum number of elements to test
            
        Returns:
            dict: Complete test results
        """
        print(f"\n{'='*60}")
        print(f"Starting Comprehensive Clickability Test")
        print(f"URL: {url}")
        print(f"Timestamp: {datetime.now()}")
        print(f"{'='*60}\n")
        
        try:
            # Find all clickable elements
            clickable_elements = self.find_clickable_elements(url)
            
            # Limit the number of elements to test
            # if len(clickable_elements) > max_elements:
            #     print(f"Limiting test to first {max_elements} elements out of {len(clickable_elements)} found")
            #     clickable_elements = clickable_elements[:max_elements]
            
            test_results = {
                'url': url,
                'total_elements_found': len(clickable_elements),
                'elements_tested': 0,
                'active_clicks': 0,
                'dead_clicks': 0,
                'errors': 0,
                'results': [],
                'summary': {},
                'timestamp': datetime.now().isoformat()
            }
            
            # Test each element
            for i, element_info in enumerate(clickable_elements, 1):
                print(f"\nTesting element {i}/{len(clickable_elements)}")
                print(f"Tag: {element_info['tag_name']}, "
                      f"Class: {element_info['class_names'][:50]}{'...' if len(element_info['class_names']) > 50 else ''}, "
                      f"Text: {element_info['text'][:30]}{'...' if len(element_info['text']) > 30 else ''}")
                # self.close_popups()
                self.driver.get(url)  # Ensure we're on the correct page
                time.sleep(2)  # Allow page to load        
                  # Always refresh the page before each test to avoid popups
             # Allow page to reload
                
                # Go back to original page if we navigated away
                if self.driver.current_url != url:
                    print("Returning to original page...")
                    self.driver.get(url)
                    time.sleep(2)
                # self.close_popups()
                result = self.test_element_click(element_info)
                test_results['results'].append(result)
                test_results['elements_tested'] += 1
                
                # Update counters
                if result['click_status'].startswith('active'):
                    test_results['active_clicks'] += 1
                    print(f"✅ ACTIVE: {result['click_status']}")
                elif result['click_status'] == 'dead_click':
                    test_results['dead_clicks'] += 1
                    print(f"❌ DEAD CLICK")
                else:
                    test_results['errors'] += 1
                    print(f"⚠️  ERROR: {result['click_status']} - {result['error_message']}")
            
            # Generate summary
            test_results['summary'] = self._generate_summary(test_results)
            
            return test_results
            
        except Exception as e:
            print(f"Error during comprehensive test: {e}")
            return {'error': str(e)}
    
    def _generate_summary(self, test_results):
        """Generate test summary statistics"""
        summary = {
            'total_tested': test_results['elements_tested'],
            'active_percentage': round((test_results['active_clicks'] / test_results['elements_tested']) * 100, 2) if test_results['elements_tested'] > 0 else 0,
            'dead_percentage': round((test_results['dead_clicks'] / test_results['elements_tested']) * 100, 2) if test_results['elements_tested'] > 0 else 0,
            'error_percentage': round((test_results['errors'] / test_results['elements_tested']) * 100, 2) if test_results['elements_tested'] > 0 else 0,
            'most_common_classes': self._get_most_common_classes(test_results['results']),
            'click_status_breakdown': self._get_click_status_breakdown(test_results['results'])
        }
        return summary
    
    def _get_most_common_classes(self, results):
        """Get most common class names from tested elements"""
        class_counts = {}
        for result in results:
            classes = result['element_info']['class_names']
            if classes:
                for class_name in classes.split():
                    class_counts[class_name] = class_counts.get(class_name, 0) + 1
        
        return sorted(class_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    def _get_click_status_breakdown(self, results):
        """Get breakdown of click statuses"""
        status_counts = {}
        for result in results:
            status = result['click_status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return status_counts
    
    def print_detailed_report(self, test_results):
        """Print detailed test report"""
        print(f"\n{'='*80}")
        print(f"DETAILED TEST REPORT")
        print(f"{'='*80}")
        
        print(f"\n📊 SUMMARY STATISTICS:")
        print(f"   Total Elements Found: {test_results['total_elements_found']}")
        print(f"   Elements Tested: {test_results['elements_tested']}")
        print(f"   Active Clicks: {test_results['active_clicks']} ({test_results['summary']['active_percentage']}%)")
        print(f"   Dead Clicks: {test_results['dead_clicks']} ({test_results['summary']['dead_percentage']}%)")
        print(f"   Errors: {test_results['errors']} ({test_results['summary']['error_percentage']}%)")
        
        print(f"\n🏷️  MOST COMMON CLASSES:")
        for class_name, count in test_results['summary']['most_common_classes'][:5]:
            print(f"   {class_name}: {count}")
        
        print(f"\n📈 CLICK STATUS BREAKDOWN:")
        for status, count in test_results['summary']['click_status_breakdown'].items():
            print(f"   {status}: {count}")
        
        print(f"\n🔍 DETAILED RESULTS:")
        for i, result in enumerate(test_results['results'][:10], 1):  # Show first 10 detailed results
            element = result['element_info']
            print(f"\n   [{i}] {element['tag_name'].upper()}")
            print(f"       Class: {element['class_names'][:80]}")
            print(f"       Text: {element['text'][:80]}")
            print(f"       Status: {result['click_status']}")
            if result['error_message']:
                print(f"       Error: {result['error_message']}")
    
    def save_results_to_file(self, test_results, filename=None):
        """Save test results to JSON file"""
        if not filename:
            # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = self.url.split('/')
            print(name[-1])
            filename = f"clickability_test_results_{name[-1]}.json"

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(test_results, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Results saved to: {filename}")
        except Exception as e:
            print(f"Error saving results: {e}")
    
    def close(self):
        """Close the browser driver"""
        if self.driver:
            self.driver.quit()
            print("Browser closed.")

def run_script_separate_drivers(url, test_name):
        """Run script with separate driver instance for each thread"""
        print(f"\n🚀 Starting test for {test_name}: {url}")
        tester = None
        try:
            tester = ClickableElementTester(headless=False, timeout=10)
            results = tester.run_comprehensive_test(url)
            
            # Print detailed report
            print(f"\n{'='*60}")
            print(f"REPORT FOR {test_name.upper()}")
            print(f"{'='*60}")
            tester.print_detailed_report(results)
            
            # Save results to file with unique name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"clickability_test_{test_name}_{timestamp}.json"
            tester.save_results_to_file(results, filename)
            
            return results
            
        except Exception as e:
            print(f"❌ Test failed for {test_name}: {e}")
            return None
        finally:
            if tester:
                tester.close()

def run_concurrent_tests_with_process_pool():
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import multiprocessing
    
    # Define test URLs
    test_urls = [
        ("https://bajajfinserv.in/personal-loan", "Personal-loan"),
        ("https://www.bajajfinserv.in/home-loan", "Home-loan"),
        ("https://www.bajajfinserv.in/gold-loan", "Gold-loan")
    ]
    
    print("🔄 Running concurrent tests with process pool...")
    
    # Limit the number of processes to avoid overwhelming the system
    max_workers = min(len(test_urls), multiprocessing.cpu_count())
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_name = {
            executor.submit(run_script_separate_drivers, url, name): name 
            for url, name in test_urls
        }
        
        results = {}
        
        # Process completed tasks
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                result = future.result()
                results[name] = result
                print(f"✅ Completed test for {name}")
            except Exception as e:
                print(f"❌ Test failed for {name}: {e}")
                results[name] = None
    
    print(f"\n✅ All concurrent tests completed!")
    return results

def main():
    """Main function to run the clickable element tester"""
    # Test URL - Bajaj Finserv Personal Loan Page
    # test_url = "https://bajajfinserv.in/personal-loan"
    # test_url = "https://www.bajajfinserv.in/gold-loan"
    # test_url = "https://www.bajajfinserv.in/doctor-world"
    # test_url = "https://www.bajajfinserv.in/insurance"
    # test_url = "https://www.bajajfinserv.in/electronics-on-emis"
    # test_url = "https://www.bajajfinserv.in/home-loan"
    

    # test_url = "https://www.bajajfinserv.in/government-schemes"
    # test_url = "https://www.aboutbajajfinserv.com/"
    test_url = "https://www.bajajfinserv.in/"
    # Initialize tester
    def run_script(url, tester):
        results = tester.run_comprehensive_test(url)
         # Print detailed report
        tester.print_detailed_report(results)
        
        # Save results to file
        tester.save_results_to_file(results)
        tester.close()

    # import threading
    
    try:
        tester = ClickableElementTester(headless=False, timeout=10)
        # print(f"Opening {test_url} in browser for manual login/signup...")
        # tester.driver.get(test_url)
        # print("⏳ You have 30 second to complete login/signup in the browser window...")
        # time.sleep(120)  # Wait 1 minute for manual login

        print("🔍 Starting clickable element detection and dead click testing...")
        results = tester.run_comprehensive_test(test_url)
        # print("⏳ You have 1 minute to complete login/signup in the browser window...")
        # time.sleep(60)  # Wait 1 minute for manual login
        # results2 = tester.run_comprehensive_test(test_url1)
        # results1 = tester.run_comprehensive_test(test_url1)
        
        # # Print detailed report
        tester.print_detailed_report(results)
        # tester.print_detailed_report(results1)
        
        # # Save results to file
        tester.save_results_to_file(results)
        # tester.save_results_to_file(results1)
        
        # thread1 = threading.Thread(target=run_script, args=(test_url1, tester))
        # thread2 = threading.Thread(target=run_script, args=(test_url2, tester))

        # thread1.start()
        # thread2.start()

        # thread1.join()
        # thread2.join()
        # results = run_concurrent_tests_with_process_pool()

    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"Test failed with error: {e}")
    # finally:
    #     # Clean up
    #     tester.close()

if __name__ == "__main__":
    main()
