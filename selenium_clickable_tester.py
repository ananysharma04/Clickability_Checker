from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import json
from datetime import datetime
import hashlib
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    TimeoutException, 
    ElementClickInterceptedException,
    StaleElementReferenceException,
    NoSuchElementException,
    WebDriverException,
    ElementNotInteractableException
)
from selenium.webdriver.chrome.options import Options
from urllib.parse import urljoin
from typing import Dict, List, Optional, Union, Set

class ClickableElementTester:
    
    
    def __init__(self, headless: bool = False, timeout: int = 10, max_workers: int = 3):
        """
        Initialize the clickable element tester
        
        Args:
            headless: Run browser in headless mode
            timeout: Default timeout for operations
            max_workers: Number of concurrent drivers (default: 3)
        """
        self.timeout = timeout
        self.max_workers = max_workers
        self.results: List[Dict] = []
        self.driver = self._setup_driver(headless)  # Main driver for finding elements
        self.url: str = ""
        self.seen_elements: Set[str] = set()
        self.headless = headless
        self.driver_pool = []


    def _setup_driver_pool(self) -> List[webdriver.Chrome]:
        """Setup a pool of Chrome WebDriver instances for concurrent testing"""
        driver_pool = []
        for i in range(self.max_workers):
            try:
                driver = self._setup_driver(self.headless)
                driver_pool.append(driver)
                print(f"Driver {i+1} initialized successfully")
            except Exception as e:
                print(f"Failed to initialize driver {i+1}: {e}")
        return driver_pool
    

    

    def _close_driver_pool(self, driver_pool: List[webdriver.Chrome]) -> None:
        """Close all drivers in the pool"""
        for i, driver in enumerate(driver_pool):
            try:
                driver.quit()
                print(f"Driver {i+1} closed")
            except Exception as e:
                print(f"Error closing driver {i+1}: {e}")
        
    
    def _divide_elements_into_batches(self, elements: List[Dict], num_batches: int = 3) -> List[List[Dict]]:
        """Divide elements into specified number of batches for concurrent processing"""
        batch_size = len(elements) // num_batches
        remainder = len(elements) % num_batches
        
        batches = []
        start_idx = 0
        
        for i in range(num_batches):
            # Add one extra element to first 'remainder' batches
            current_batch_size = batch_size + (1 if i < remainder else 0)
            end_idx = start_idx + current_batch_size
            
            batch = elements[start_idx:end_idx]
            if batch:  # Only add non-empty batches
                batches.append(batch)
            
            start_idx = end_idx
        
        return batches

    def _test_element_batch(self, batch: List[Dict], driver: webdriver.Chrome, 
                       batch_id: int, url: str) -> List[Dict]:
        """Test a batch of elements using a specific driver"""
        batch_results = []
        
        print(f"\n🔄 Batch {batch_id} starting - {len(batch)} elements")
        
        for i, element_info in enumerate(batch, 1):
            try:
                # Ensure we're on the correct page
                if driver.current_url != url:
                    driver.get(url)
                    time.sleep(2)
                
                print(f"Batch {batch_id} - Testing element {i}/{len(batch)}")
                print(f"  Tag: {element_info['tag_name']}, "
                    f"Class: {element_info['class_names'][:30]}{'...' if len(element_info['class_names']) > 30 else ''}")
                
                # Test the element using the batch driver
                result = self._test_element_click_with_driver(element_info, driver, url)
                batch_results.append(result)
                
                # Log result
                if result['click_status'].startswith('active'):
                    print(f"  ✅ ACTIVE: {result['click_status']}")
                elif result['click_status'] == 'dead_click':
                    print(f"  ❌ DEAD CLICK")
                else:
                    print(f"  ⚠️  ERROR: {result['click_status']}")
                    
            except Exception as e:
                print(f"  Error testing element in batch {batch_id}: {e}")
                error_result = {
                    'element_info': element_info,
                    'click_status': 'batch_error',
                    'error_message': str(e),
                    'page_changed': False,
                    'url_before': url,
                    'url_after': url,
                    'new_elements_appeared': False,
                    'timestamp': datetime.now().isoformat()
                }
                batch_results.append(error_result)
        
        print(f"✅ Batch {batch_id} completed - {len(batch_results)} results")
        return batch_results
        

    def _test_element_click_with_driver(self, element_info: Dict, driver: webdriver.Chrome, 
                                  original_url: str) -> Dict:
        """Test element click using a specific driver instance"""
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
            initial_url = driver.current_url
            initial_title = driver.title
            result['url_before'] = initial_url
            
            # Find the element using the specific driver
            element = self._find_element_by_info_with_driver(element_info, driver)
            
            if not element:
                result['click_status'] = 'element_not_found'
                result['error_message'] = 'Element could not be located for clicking'
                return result
            
            # For carousel elements, ensure they're visible before clicking
            if element_info.get('is_carousel_element', False):
                self._make_carousel_element_clickable_with_driver(element, driver)
            
            # Scroll element into view
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(1)
            
            # Check if element is still clickable
            if not (element.is_displayed() and element.is_enabled()):
                result['click_status'] = 'not_clickable'
                result['error_message'] = 'Element is not displayed or enabled'
                return result
            
            # Attempt to click the element
            try:
                element.click()
                click_successful = True
            except ElementClickInterceptedException:
                try:
                    driver.execute_script("arguments[0].click();", element)
                    click_successful = True
                except Exception as js_error:
                    result['click_status'] = 'click_intercepted'
                    result['error_message'] = f'Click intercepted: {str(js_error)}'
                    return result
            
            # Wait for changes
            time.sleep(2)
            
            # Check for changes after click
            current_url = driver.current_url
            current_title = driver.title
            result['url_after'] = current_url
            
            # Determine click status
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
                    modals = driver.find_elements(By.CSS_SELECTOR, 
                        '.modal, .popup, .overlay, .dialog, [role="dialog"], [role="alertdialog"]')
                    
                    dropdowns = driver.find_elements(By.CSS_SELECTOR,
                        '.dropdown-menu, .menu-open, [aria-expanded="true"]')
                    
                    if modals or dropdowns:
                        result['click_status'] = 'active_ui_change'
                        result['new_elements_appeared'] = True
                    else:
                        result['click_status'] = 'dead_click'
                except Exception:
                    result['click_status'] = 'dead_click'
            
        except Exception as e:
            result['click_status'] = 'error'
            result['error_message'] = str(e)
        
        return result
        

    def _find_element_by_info_with_driver(self, element_info: Dict, driver: webdriver.Chrome) -> Optional[webdriver.remote.webelement.WebElement]:
        """Find element using stored information with a specific driver"""
        strategies = [
            (By.ID, element_info['id']) if element_info['id'] else None,
            (By.XPATH, element_info['xpath']) if element_info['xpath'] != 'xpath_unavailable' else None,
            (By.CSS_SELECTOR, f".{element_info['class_names'].replace(' ', '.')}") if element_info['class_names'] else None,
        ]
        
        for strategy in strategies:
            if strategy:
                try:
                    elements = driver.find_elements(*strategy)
                    for element in elements:
                        if (element.is_displayed() and 
                            element.tag_name == element_info['tag_name'] and
                            element.text.strip()[:100] == element_info['text']):
                            return element
                except Exception:
                    continue
        
        return None
    
    def _make_carousel_element_clickable_with_driver(self, element, driver: webdriver.Chrome) -> None:
        """Make a carousel element visible and clickable using specific driver"""
        try:
            driver.execute_script("""
                var element = arguments[0];
                var current = element;
                
                while (current && current !== document.body) {
                    current.style.display = 'block';
                    current.style.visibility = 'visible';
                    current.style.opacity = '1';
                    current.style.position = 'relative';
                    current.style.zIndex = 'auto';
                    current.style.transform = current.style.webkitTransform = 'none';
                    current = current.parentElement;
                }
            """, element)
            
            time.sleep(0.5)
        except Exception as e:
            print(f"Error making carousel element clickable: {e}")

    
    def run_comprehensive_test_concurrent(self, url: str) -> Dict:
        """Run comprehensive test on all clickable elements using concurrent processing"""
        print(f"\n{'='*60}")
        print(f"Starting Concurrent Comprehensive Clickability Test")
        print(f"URL: {url}")
        print(f"Max Workers: {self.max_workers}")
        print(f"Timestamp: {datetime.now()}")
        print(f"{'='*60}\n")
        
        try:
            # Find all clickable elements using main driver
            print("🔍 Finding all clickable elements...")
            clickable_elements = self.find_clickable_elements(url)
            print(f"Found {len(clickable_elements)} clickable elements")
            
            # Setup driver pool
            print(f"\n🚀 Setting up {self.max_workers} concurrent drivers...")
            driver_pool = self._setup_driver_pool()
            
            if not driver_pool:
                raise Exception("Failed to initialize driver pool")
            
            # Divide elements into batches
            batches = self._divide_elements_into_batches(clickable_elements, len(driver_pool))
            print(f"Elements divided into {len(batches)} batches")
            for i, batch in enumerate(batches):
                print(f"  Batch {i+1}: {len(batch)} elements")
            
            # Initialize test results
            test_results = {
                'url': url,
                'total_elements_found': len(clickable_elements),
                'elements_tested': 0,
                'active_clicks': 0,
                'dead_clicks': 0,
                'errors': 0,
                'results': [],
                'concurrent_info': {
                    'max_workers': self.max_workers,
                    'batches_created': len(batches),
                    'batch_sizes': [len(batch) for batch in batches]
                },
                'summary': {},
                'timestamp': datetime.now().isoformat()
            }
            
            # Process batches concurrently
            print(f"\n🏃‍♂️ Starting concurrent testing...")
            start_time = time.time()
            
            with ThreadPoolExecutor(max_workers=len(driver_pool)) as executor:
                # Submit batch processing tasks
                future_to_batch = {
                    executor.submit(self._test_element_batch, batch, driver_pool[i], i+1, url): i
                    for i, batch in enumerate(batches)
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_batch):
                    batch_id = future_to_batch[future]
                    try:
                        batch_results = future.result()
                        test_results['results'].extend(batch_results)
                        test_results['elements_tested'] += len(batch_results)
                        print(f"✅ Batch {batch_id + 1} results collected")
                    except Exception as e:
                        print(f"❌ Batch {batch_id + 1} failed: {e}")
            
            end_time = time.time()
            test_results['concurrent_info']['total_time'] = round(end_time - start_time, 2)
            
            # Count results
            for result in test_results['results']:
                if result['click_status'].startswith('active'):
                    test_results['active_clicks'] += 1
                elif result['click_status'] == 'dead_click':
                    test_results['dead_clicks'] += 1
                else:
                    test_results['errors'] += 1
            
            # Generate summary
            test_results['summary'] = self._generate_summary(test_results)
            
            # Cleanup
            self._close_driver_pool(driver_pool)
            
            print(f"\n🎉 Concurrent testing completed in {test_results['concurrent_info']['total_time']} seconds")
            print(f"Total elements tested: {test_results['elements_tested']}")
            print(f"Active clicks: {test_results['active_clicks']}")
            print(f"Dead clicks: {test_results['dead_clicks']}")
            print(f"Errors: {test_results['errors']}")
            
            return test_results
            
        except Exception as e:
            print(f"Error during concurrent comprehensive test: {e}")
            # Cleanup on error
            if 'driver_pool' in locals():
                self._close_driver_pool(driver_pool)
            return {'error': str(e)}

    def close(self) -> None:
        """Close the main browser driver"""
        if self.driver:
            self.driver.quit()
            print("Main browser closed.")

    
            
    def _setup_driver(self, headless: bool) -> webdriver.Chrome:
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

    def _handle_carousel_banner(self, element) -> List[Dict]:
        """Handle auto-scrolling carousels and banners by pausing them and collecting all slides"""
        carousel_elements = []
        
        try:
            carousel_container = self.driver.execute_script("""
                var element = arguments[0];
                var current = element;
                var carouselSelectors = [
                    'carousel', 'slider', 'banner-slider', 'swiper', 'slick',
                    'owl-carousel', 'hero-banner', 'banner-container', 'slideshow'
                ];
                
                while (current && current !== document.body) {
                    var className = current.className || '';
                    var dataRide = current.getAttribute('data-ride') || '';
                    
                    for (var i = 0; i < carouselSelectors.length; i++) {
                        if (className.includes(carouselSelectors[i]) || dataRide === 'carousel') {
                            return current;
                        }
                    }
                    current = current.parentElement;
                }
                return null;
            """, element)
            
            if carousel_container:
                print("Found carousel container, attempting to pause auto-scroll")
                self._pause_carousel(carousel_container)
                
                slides = self._get_all_carousel_slides(carousel_container)
                for slide in slides:
                    carousel_elements.extend(self._extract_clickables_from_slide(slide))
                    
        except Exception as e:
            print(f"Error handling carousel: {e}")
            
        return carousel_elements

    def _pause_carousel(self, carousel_container) -> None:
        """Pause carousel auto-scrolling using various methods"""
        try:
            self.driver.execute_script("""
                var carousel = arguments[0];
                // Bootstrap/jQuery
                if (typeof jQuery !== 'undefined' && jQuery(carousel).carousel) {
                    jQuery(carousel).carousel('pause');
                }
                if (carousel.carousel && typeof carousel.carousel === 'function') {
                    carousel.carousel('pause');
                }
                
                // CSS animations
                carousel.style.animationPlayState = carousel.style.webkitAnimationPlayState = 'paused';
                
                // Pause all child animations
                var children = carousel.querySelectorAll('*');
                for (var i = 0; i < children.length; i++) {
                    children[i].style.animationPlayState = children[i].style.webkitAnimationPlayState = 'paused';
                }
                
                // Clear intervals and stop slider libraries
                if (window.sliderIntervals) window.sliderIntervals.forEach(clearInterval);
                if (carousel.swiper) carousel.swiper.autoplay.stop();
                if (carousel.slick) jQuery(carousel).slick('slickPause');
            """, carousel_container)
            
            time.sleep(1)  # Allow pause to take effect
        except Exception as e:
            print(f"Could not pause carousel: {e}")

    def _get_all_carousel_slides(self, carousel_container) -> List[webdriver.remote.webelement.WebElement]:
        """Get all slides from a carousel, including hidden ones"""
        slide_selectors = [
            '.carousel-item', '.slide', '.slider-item', '.swiper-slide',
            '.slick-slide', '.banner-slide', '.owl-item', '[data-slide]',
            '.glide__slide', '.splide__slide', '.flickity-cell',
            '.keen-slider__slide', '.embla__slide', '.tns-item',
            '.carousel-cell', '.slider-slide', '.slide-item',
            '[class*="slide"]', '[data-slide-index]', '[data-slide-id]'
        ]
        
        slides = []
        for selector in slide_selectors:
            try:
                found_slides = carousel_container.find_elements(By.CSS_SELECTOR, selector)
                if found_slides:
                    slides.extend(found_slides)
                    break
            except Exception:
                continue
        
        if not slides:
            try:
                potential_slides = carousel_container.find_elements(By.CSS_SELECTOR, 'div, section, article, li')
                slides = [slide for slide in potential_slides if self._looks_like_slide(slide)]
            except Exception:
                pass

        if not slides:
            try:
                nested_containers = carousel_container.find_elements(By.CSS_SELECTOR, 
                    '.swiper-wrapper, .slider-wrapper, .carousel-inner, .slides')
                for container in nested_containers:
                    nested_slides = container.find_elements(By.CSS_SELECTOR, 'div, li')
                    slides.extend(slide for slide in nested_slides if self._looks_like_slide(slide))
            except Exception:
                pass
        
        print(f"Found {len(slides)} carousel slides")
        return slides

    def _looks_like_slide(self, element) -> bool:
        """Check if an element looks like a carousel slide"""
        try:
            # Check for typical slide content
            has_content = (
                len(element.find_elements(By.TAG_NAME, 'img')) > 0 or
                len(element.text.strip()) > 20 or
                len(element.find_elements(By.TAG_NAME, 'a')) > 0 or
                len(element.find_elements(By.TAG_NAME, 'button')) > 0
            )
            
            if has_content:
                return True
                
            # Check for slide-like styling or class names
            style = element.get_attribute('style') or ''
            class_names = element.get_attribute('class') or ''
            
            computed_style = self.driver.execute_script("""
                var style = window.getComputedStyle(arguments[0]);
                return {
                    position: style.position,
                    float: style.float,
                    display: style.display
                };
            """, element)
            
            has_slide_styling = (
                'width:' in style.lower() or 
                computed_style.get('position') in ['absolute', 'relative'] or
                computed_style.get('float') in ['left', 'right'] or
                computed_style.get('display') in ['flex', 'inline-block']
            )
            
            has_slide_class = any(keyword in class_names.lower() for keyword in 
                                ['slide', 'item', 'cell', 'panel', 'tab'])
            
            return has_slide_styling or has_slide_class
        except Exception:
            return False

    def _extract_clickables_from_slide(self, slide) -> List[Dict]:
        """Extract clickable elements from a single slide"""
        clickables = []
        
        try:
            # Make slide visible if hidden
            self.driver.execute_script("""
                var slide = arguments[0];
                slide.style.display = 'block';
                slide.style.visibility = 'visible';
                slide.style.opacity = '1';
                slide.style.transform = 'translateX(0px)';
                slide.style.position = 'relative';
                slide.style.zIndex = '1000';
            """, slide)
            
            time.sleep(1)

            # Find clickable elements in this slide
            clickable_selectors = [
                'a', 'button', '[onclick]', '[role="button"]', 'input[type="button"]',
                'input[type="submit"]', '.btn', '.button', '.link', '.cta', '.call-to-action',
                '[data-action]', '[data-click]', '[data-href]',
                '.carousel-control', '.slider-nav', '.slide-nav',
                '.prev', '.next', '.slide-btn', '.carousel-btn',
                '.thumbnail__overlay'
            ]
            
            for selector in clickable_selectors:
                try:
                    elements = slide.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_enabled():
                            element_info = self._extract_element_info_for_hidden(element)
                            if element_info:
                                clickables.append(element_info)
                except Exception:
                    continue

            # Find elements by common action words in their text
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
                except Exception:
                    continue

        except Exception as e:
            print(f"Error extracting clickables from slide: {e}")

        return clickables

    def _extract_element_info_for_hidden(self, element) -> Optional[Dict]:
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
            
            href = element.get_attribute('href') or ''
            element_info = {
                'tag_name': element.tag_name,
                'text': element.text.strip()[:100] if element.text else '',
                'class_names': element.get_attribute('class') or '',
                'id': element.get_attribute('id') or '',
                'href': href,
                'status_code': self.get_status_code(href),
                'onclick': element.get_attribute('onclick') or '',
                'role': element.get_attribute('role') or '',
                'type': element.get_attribute('type') or '',
                'data_testid': element.get_attribute('data-testid') or '',
                'aria_label': element.get_attribute('aria-label') or '',
                'xpath': self._get_element_xpath(element),
                'location': element.location,
                'size': element.size,
                'is_displayed': True,
                'is_enabled': element.is_enabled(),
                'is_carousel_element': True
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

    def _is_duplicate_element(self, element_info: Dict, existing_elements: List[Dict]) -> bool:
        """Check for duplicate elements more accurately"""
        for existing in existing_elements:
            if (existing['xpath'] == element_info['xpath'] or
                (existing['unique_id'] == element_info['unique_id'] and
                existing['tag_name'] == element_info['tag_name'] and
                existing['text'] == element_info['text'])):
                return True
        return False

    def find_clickable_elements(self, url: str) -> List[Dict]:
        """Find all potentially clickable elements on the page"""
        self.url = url
        print(f"Loading URL: {url}")
        self.driver.get(url)
        
        try:
            WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            print("⚠️ Page load timeout - proceeding with available elements")
        
        time.sleep(5)  # Allow additional time for dynamic content

        header_footer_selectors = [
            'header', 'nav', 'footer',
            '.header', '.nav', '.footer', '.navigation',
            '#header', '#nav', '#footer', '#navigation',
            '[role="banner"]', '[role="navigation"]', '[role="contentinfo"]',
            '.site-header', '.site-footer', '.page-header', '.page-footer',
            '.main-header', '.main-footer', '.top-nav', '.bottom-nav',
            '.navbar', '.nav-bar', '.site-nav', '.primary-nav'
        ]
        
        main_content_area = self._get_main_content_area()
        carousel_elements = self._find_carousel_elements(main_content_area, header_footer_selectors)
        clickable_elements = self._find_regular_clickables(main_content_area, header_footer_selectors)
        
        clickable_elements.extend(carousel_elements)
        print(f"Found {len(clickable_elements)} potentially clickable elements")
        return clickable_elements

    def _find_carousel_elements(self, main_content_area, header_footer_selectors) -> List[Dict]:
        """Find and process carousel elements"""
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
            '.thumbnail__overlay'
        ]
        
        for selector in carousel_selectors:
            try:
                carousels = (main_content_area.find_elements(By.CSS_SELECTOR, selector) 
                            if main_content_area 
                            else self.driver.find_elements(By.CSS_SELECTOR, selector))
                
                for carousel in carousels:
                    try:
                        if carousel.is_displayed() and not self._is_in_header_or_footer(carousel, header_footer_selectors):
                            print(f"Processing carousel with selector: {selector}")
                            carousel_elements.extend(self._handle_carousel_banner(carousel))
                    except StaleElementReferenceException:
                        continue
                    except Exception as e:
                        print(f"Error processing carousel element: {e}")
            except Exception as e:
                print(f"Error processing carousel selector '{selector}': {e}")
        
        return carousel_elements

    def _find_regular_clickables(self, main_content_area, header_footer_selectors) -> List[Dict]:
        """Find regular clickable elements (non-carousel)"""
        clickable_selectors = [
            'a', 'button', 
            'input[type="button"]', 'input[type="submit"]', 'input[type="reset"]',
            '[onclick]', '[onmousedown]', '[onmouseup]', '[ondblclick]',
            '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
            '[role="option"]', '[role="treeitem"]', '[role="gridcell"]',
            '[tabindex="0"]', '[tabindex="-1"]', 'div[tabindex]', 'span[tabindex]',
            'li[tabindex]', 'td[tabindex]', 'th[tabindex]',
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
            '[data-action]', '[data-click]', '[data-href]', '[data-url]',
            '[data-toggle]', '[data-target]', '[data-dismiss]',
            '[data-testid*="button"]', '[data-testid*="link"]', '[data-testid*="click"]',
            '[data-cy*="button"]', '[data-cy*="link"]', '[data-cy*="click"]',
            'select', 'input[type="checkbox"]', 'input[type="radio"]',
            'input[type="file"]', 'input[type="image"]',
            '[class*="btn"]', '[class*="button"]', '[class*="link"]',
            '[class*="click"]', '[class*="action"]', '[class*="cta"]',
            '[id*="btn"]', '[id*="button"]', '[id*="link"]',
            'video[controls]', 'audio[controls]',
            'li[onclick]', 'td[onclick]', 'tr[onclick]',
            'li[role="button"]', 'td[role="button"]', 'tr[role="button"]',
            'svg[onclick]', 'svg[role="button"]',
            'area', 'img[onclick]', 'img[role="button"]',
            'div[role="button"]', 'span[role="button"]',
            'p[role="button"]', 'section[role="button"]',
            '.thumbnail__overlay'
        ]
        
        unique_ids = set()
        clickable_elements = []
        
        for selector in clickable_selectors:
            try:
                elements = (main_content_area.find_elements(By.CSS_SELECTOR, selector) 
                          if main_content_area 
                          else self.driver.find_elements(By.CSS_SELECTOR, selector))
                
                for element in elements:
                    try:
                        if (element.is_displayed() and element.is_enabled() and
                            not self._is_in_header_or_footer(element, header_footer_selectors) and
                            not self._is_carousel_element(element)):
                                
                            element_info = self._extract_element_info(element)
                            if element_info and element_info['unique_id'] not in unique_ids:
                                unique_ids.add(element_info['unique_id'])
                                clickable_elements.append(element_info)
                    except StaleElementReferenceException:
                        continue
                    except Exception as e:
                        print(f"Error processing element: {e}")
            except Exception as e:
                print(f"Error finding elements with selector '{selector}': {e}")
        
        # Additional detection methods
        clickable_elements.extend(self._find_elements_by_pointer_cursor(header_footer_selectors))
        clickable_elements.extend(self._find_elements_by_event_listeners(header_footer_selectors))
        
        return clickable_elements

    def _find_elements_by_pointer_cursor(self, header_footer_selectors) -> List[Dict]:
        """Find elements with pointer cursor styling"""
        elements = []
        try:
            pointer_elements = self.driver.execute_script("""
                return Array.from(document.querySelectorAll('*')).filter(el => {
                    return window.getComputedStyle(el).cursor === 'pointer' && 
                           el.offsetWidth > 0 && 
                           el.offsetHeight > 0;
                });
            """)
            
            for element in pointer_elements:
                try:
                    if (element.is_displayed() and element.is_enabled() and
                        not self._is_in_header_or_footer(element, header_footer_selectors) and
                        not self._is_carousel_element(element)):
                            
                        element_info = self._extract_element_info(element)
                        if element_info:
                            element_info['detection_method'] = 'pointer_cursor'
                            elements.append(element_info)
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"Error finding pointer cursor elements: {e}")
            
        return elements

    def _find_elements_by_event_listeners(self, header_footer_selectors) -> List[Dict]:
        """Find elements with click event listeners"""
        elements = []
        try:
            listener_elements = self.driver.execute_script("""
                return Array.from(document.querySelectorAll('*')).filter(el => {
                    return el.onclick || 
                           el.onmousedown || 
                           el.onmouseup ||
                           el.getAttribute('onclick') ||
                           el.hasAttribute('data-action') ||
                           el.hasAttribute('data-click') ||
                           el.hasAttribute('data-href');
                });
            """)
            
            for element in listener_elements:
                try:
                    if (element.is_displayed() and element.is_enabled() and
                        not self._is_in_header_or_footer(element, header_footer_selectors) and
                        not self._is_carousel_element(element)):
                            
                        element_info = self._extract_element_info(element)
                        if element_info:
                            element_info['detection_method'] = 'event_listener'
                            elements.append(element_info)
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"Error finding event listener elements: {e}")
            
        return elements

    def _get_main_content_area(self) -> Optional[webdriver.remote.webelement.WebElement]:
        """Identify and return the main content area of the page"""
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
            except Exception:
                continue
        
        print("No specific main content area found, will use exclusion method")
        return None
    
    def _is_in_header_or_footer(self, element, header_footer_selectors) -> bool:
        """Check if an element is within header or footer sections"""
        try:
            # Check element itself
            element_tag = element.tag_name.lower()
            if element_tag in ['header', 'nav', 'footer']:
                return True
            
            # Check element attributes
            element_class = element.get_attribute('class') or ''
            element_id = element.get_attribute('id') or ''
            element_role = element.get_attribute('role') or ''
            
            # Check for header/footer indicators
            header_footer_keywords = [
                'header', 'nav', 'navigation', 'navbar', 'nav-bar', 'footer',
                'site-header', 'site-footer', 'page-header', 'page-footer',
                'main-header', 'main-footer', 'top-nav', 'bottom-nav',
                'primary-nav', 'secondary-nav', 'breadcrumb'
            ]
            
            element_attributes = f"{element_class} {element_id}".lower()
            if any(keyword in element_attributes for keyword in header_footer_keywords):
                return True
            
            # Check ARIA roles
            if element_role in ['banner', 'navigation', 'contentinfo']:
                return True
            
            # Check parent elements
            return self.driver.execute_script("""
                var element = arguments[0];
                var current = element;
                var keywords = ['header', 'nav', 'navigation', 'navbar', 'nav-belt', 
                               'footer', 'navfooter', 'site-header', 'site-footer',
                               'page-header', 'page-footer', 'main-header', 'main-footer'];
                
                while (current && current !== document.body) {
                    var tagName = current.tagName ? current.tagName.toLowerCase() : '';
                    var className = current.className || '';
                    var id = current.id || '';
                    var role = current.getAttribute('role') || '';
                    
                    // Check tag names
                    if (['header', 'nav', 'footer'].includes(tagName)) return true;
                    
                    // Check roles
                    if (['banner', 'navigation', 'contentinfo'].includes(role)) return true;
                    
                    // Check class names and IDs
                    var attributes = (className + ' ' + id).toLowerCase();
                    if (keywords.some(k => attributes.includes(k))) return true;
                    
                    current = current.parentElement;
                }
                
                return false;
            """, element)
                
        except Exception as e:
            print(f"Error checking if element is in header/footer: {e}")
            return False
    
    def _is_carousel_element(self, element) -> bool:
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
                    if (carouselSelectors.some(sel => className.includes(sel)))) {
                        return true;
                    }
                    current = current.parentElement;
                }
                return false;
            """, element)
        except Exception:
            return False

    def get_status_code(self, href: str) -> Optional[List[int]]:
        """Return HTTP status code for the given href, or None if not applicable."""
        if not href or href.startswith(('#', 'javascript:')):
            return None
            
        try:
            # Handle relative URLs
            if href.startswith('/'):
                href = urljoin(self.url, href)
                
            response = requests.head(href, allow_redirects=True, timeout=5)
            return [r.status_code for r in response.history] + [response.status_code]
        except Exception:
            return None
        
    def _extract_element_info(self, element) -> Optional[Dict]:
        """Extract and deduplicate element info based on unique content signature."""
        try:
            # Extract key info
            tag_name = element.tag_name
            text = element.text.strip()[:100] if element.text else ''
            class_names = element.get_attribute('class') or ''
            href = element.get_attribute('href') or ''
            onclick = element.get_attribute('onclick') or ''
            element_id = element.get_attribute('id') or ''

            # Create deduplication key
            dedup_key = f"{tag_name}|{text}|{href}|{class_names}|{element_id}"
            unique_id = hashlib.md5(dedup_key.encode()).hexdigest()

            # Deduplication
            if unique_id in self.seen_elements:
                return None
            self.seen_elements.add(unique_id)

            # Final full element info
            element_info = {
                'tag_name': tag_name,
                'text': text,
                'class_names': class_names,
                'id': element_id,
                'href': href,
                'onclick': onclick,
                'status_code': self.get_status_code(href),
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
        
    def _get_element_xpath(self, element) -> str:
        """Generate XPath for an element"""
        try:
            return self.driver.execute_script("""
                function getXPath(element) {
                    if (element.id !== '') return '//*[@id=\"' + element.id + '\"]';
                    if (element === document.body) return '/html/body';
                    var ix = 0;
                    var siblings = element.parentNode.childNodes;
                    for (var i = 0; i < siblings.length; i++) {
                        var sibling = siblings[i];
                        if (sibling === element) return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                        if (sibling.nodeType === 1 && sibling.tagName === element.tagName) ix++;
                    }
                }
                return getXPath(arguments[0]);
            """, element)
        except Exception:
            return "xpath_unavailable"
    
    def _get_element_css_selector(self, element) -> str:
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
    
    def _create_unique_id(self, element_info: Dict) -> int:
        """Create a unique identifier for an element"""
        components = [
            element_info['tag_name'],
            element_info['id'],
            element_info['class_names'],
            element_info['text'][:50],
            str(element_info['location']),
        ]
        return hash('|'.join(str(c) for c in components))
    
    def is_dead_click_by_href(self, element_info: Dict) -> bool:
        """Returns True if the element is a dead click based on href."""
        href = (element_info.get('href') or '').replace(' ', '').lower()
        return href in ['javascript:void(0)', 'javascript::void(0)', '#', ' ']
    
    def test_element_click(self, element_info: Dict) -> Dict:
        """Test if an element click is functional or dead - with carousel support"""
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
            
            # Find the element
            element = (self._find_and_prepare_carousel_element(element_info) 
                      if element_info.get('is_carousel_element', False) 
                      else self._find_element_by_info(element_info))
            
            if not element:
                result['click_status'] = 'element_not_found'
                result['error_message'] = 'Element could not be located for clicking'
                return result
            
            # For carousel elements, ensure they're visible before clicking
            if element_info.get('is_carousel_element', False):
                self._make_carousel_element_clickable(element)
            
            # Scroll element into view
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(1)
            
            # Check if element is still clickable
            if not (element.is_displayed() and element.is_enabled()):
                result['click_status'] = 'not_clickable'
                result['error_message'] = 'Element is not displayed or enabled'
                return result
            
            # Attempt to click the element
            try:
                element.click()
                click_successful = True
            except ElementClickInterceptedException:
                try:
                    self.driver.execute_script("arguments[0].click();", element)
                    click_successful = True
                except Exception as js_error:
                    result['click_status'] = 'click_intercepted'
                    result['error_message'] = f'Click intercepted: {str(js_error)}'
                    return result
            
            # Wait for changes
            time.sleep(2)
            
            # Check for changes after click
            current_url = self.driver.current_url
            current_title = self.driver.title
            result['url_after'] = current_url
            
            # Determine click status
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

    def _find_and_prepare_carousel_element(self, element_info: Dict) -> Optional[webdriver.remote.webelement.WebElement]:
        """Find carousel element and make it ready for clicking"""
        try:
            carousel_containers = self.driver.find_elements(By.CSS_SELECTOR, 
                '.carousel, .slider, .banner-slider, .swiper, .slick, [data-ride="carousel"], ' +
                '.owl-carousel, .swiper-container, .glide, .splide, .flickity, ' +
                '[class*="carousel"], [class*="slider"], [class*="swiper"]'
            )
            
            for container in carousel_containers:
                self._pause_carousel(container)
                element = self._find_element_by_info_in_container(element_info, container)
                if element:
                    return element
            
            return None
        except Exception as e:
            print(f"Error finding carousel element: {e}")
            return None

    def _find_element_by_info_in_container(self, element_info: Dict, container) -> Optional[webdriver.remote.webelement.WebElement]:
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

    def _make_carousel_element_clickable(self, element) -> None:
        """Make a carousel element visible and clickable"""
        try:
            self.driver.execute_script("""
                var element = arguments[0];
                var current = element;
                
                while (current && current !== document.body) {
                    current.style.display = 'block';
                    current.style.visibility = 'visible';
                    current.style.opacity = '1';
                    current.style.position = 'relative';
                    current.style.zIndex = 'auto';
                    current.style.transform = current.style.webkitTransform = 'none';
                    current = current.parentElement;
                }
            """, element)
            
            time.sleep(0.5)  # Allow styles to apply
        except Exception as e:
            print(f"Error making carousel element clickable: {e}")

    def _find_element_by_info(self, element_info: Dict) -> Optional[webdriver.remote.webelement.WebElement]:
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

    def run_comprehensive_test(self, url: str) -> Dict:
        """Run comprehensive test on all clickable elements"""
        print(f"\n{'='*60}")
        print(f"Starting Comprehensive Clickability Test")
        print(f"URL: {url}")
        print(f"Timestamp: {datetime.now()}")
        print(f"{'='*60}\n")
        
        try:
            clickable_elements = self.find_clickable_elements(url)
            
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
            
            for i, element_info in enumerate(clickable_elements, 1):
                print(f"\nTesting element {i}/{len(clickable_elements)}")
                print(f"Tag: {element_info['tag_name']}, "
                      f"Class: {element_info['class_names'][:50]}{'...' if len(element_info['class_names']) > 50 else ''}, "
                      f"Text: {element_info['text'][:30]}{'...' if len(element_info['text']) > 30 else ''}")
                
                self.driver.get(url)  # Ensure we're on the correct page
                time.sleep(2)  # Allow page to load        
                
                # Go back to original page if we navigated away
                if self.driver.current_url != url:
                    print("Returning to original page...")
                    self.driver.get(url)
                    time.sleep(2)
                
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
    
    def _generate_summary(self, test_results: Dict) -> Dict:
        """Generate test summary statistics"""
        total = test_results['elements_tested']
        return {
            'total_tested': total,
            'active_percentage': round((test_results['active_clicks'] / total) * 100, 2) if total > 0 else 0,
            'dead_percentage': round((test_results['dead_clicks'] / total) * 100, 2) if total > 0 else 0,
            'error_percentage': round((test_results['errors'] / total) * 100, 2) if total > 0 else 0,
            'most_common_classes': self._get_most_common_classes(test_results['results']),
            'click_status_breakdown': self._get_click_status_breakdown(test_results['results'])
        }
    
    def _get_most_common_classes(self, results: List[Dict]) -> List[tuple]:
        """Get most common class names from tested elements"""
        class_counts = {}
        for result in results:
            classes = result['element_info']['class_names']
            if classes:
                for class_name in classes.split():
                    class_counts[class_name] = class_counts.get(class_name, 0) + 1
        
        return sorted(class_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    def _get_click_status_breakdown(self, results: List[Dict]) -> Dict:
        """Get breakdown of click statuses"""
        status_counts = {}
        for result in results:
            status = result['click_status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return status_counts
    
    def print_detailed_report(self, test_results: Dict) -> None:
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
        for i, result in enumerate(test_results['results'][:10], 1):
            element = result['element_info']
            print(f"\n   [{i}] {element['tag_name'].upper()}")
            print(f"       Class: {element['class_names'][:80]}")
            print(f"       Text: {element['text'][:80]}")
            print(f"       Status: {result['click_status']}")
            if result['error_message']:
                print(f"       Error: {result['error_message']}")
    
    def save_results_to_file(self, test_results: Dict, filename: str = None) -> None:
        """Save test results to JSON file"""
        if not filename:
            name = self.url.split('/')[-1]
            filename = f"clickability_test_results_{name}.json"

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(test_results, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Results saved to: {filename}")
        except Exception as e:
            print(f"Error saving results: {e}")
    
    def close(self) -> None:
        """Close the browser driver"""
        if self.driver:
            self.driver.quit()
            print("Browser closed.")

def main():
    """Main function to run the concurrent clickable element tester"""
    test_url = "https://www.bajajfinserv.in/gold-loan"
    # test_url = "https://cont-sites.bajajfinserv.in/personal-loan"
    
    try:
        # Initialize with 3 concurrent workers
        tester = ClickableElementTester(headless=False, timeout=10, max_workers=3)
        
        # Run concurrent test
        results = tester.run_comprehensive_test_concurrent(test_url)
        
        # Print and save results
        tester.print_detailed_report(results)
        tester.save_results_to_file(results)
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"Test failed with error: {e}")
    finally:
        tester.close()

if __name__ == "__main__":
    main()
