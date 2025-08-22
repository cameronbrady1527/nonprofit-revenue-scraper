import logging
import base64
import time
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import google.generativeai as genai
from io import BytesIO

logger = logging.getLogger(__name__)

class FinancialDataResponse(BaseModel):
    """Pydantic model for structured financial data response from Gemini"""
    total_revenue: Optional[float] = Field(None, description="Total revenue amount")
    total_executive_compensation: Optional[float] = Field(None, description="Total executive compensation amount")
    confidence_level: str = Field("low", description="Confidence level: high, medium, low")
    notes: Optional[str] = Field(None, description="Any relevant notes or issues found")

class GeminiPDFParser:
    """
    PDF parser that uses Google's Gemini AI to extract financial data from Form 990 PDFs.
    This serves as an alternative to OCR-based parsing.
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize the Gemini PDF parser.
        
        Args:
            api_key: Google AI API key. If None, expects GOOGLE_AI_API_KEY environment variable.
        """
        import os
        
        if api_key:
            genai.configure(api_key=api_key)
        else:
            # Load from environment variable
            env_api_key = os.getenv('GOOGLE_AI_API_KEY')
            if env_api_key:
                genai.configure(api_key=env_api_key)
                logger.debug("Configured Gemini with API key from environment")
            else:
                logger.error("No GOOGLE_AI_API_KEY found in environment variables")
                raise ValueError("GOOGLE_AI_API_KEY environment variable not found")
            
        self.model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
        
    def _convert_pdf_to_base64(self, pdf_bytes: bytes) -> str:
        """Convert PDF bytes to base64 string for Gemini API."""
        return base64.b64encode(pdf_bytes).decode('utf-8')
    
    def _create_prompt(self) -> str:
        """Create the prompt for Gemini to extract financial data."""
        return """
You are analyzing a nonprofit Form 990 tax filing PDF. Please extract the following specific information:

1. **Total Revenue**: Look for the total revenue amount (usually found in Part I, line 12 or Part VIII)
2. **Total Executive Compensation**: Look for the sum of all executive compensation amounts (usually found in Part VII)

Please provide your response in the following JSON format:
{
    "total_revenue": <number_or_null>,
    "total_executive_compensation": <number_or_null>,
    "confidence_level": "<high|medium|low>",
    "notes": "<any relevant observations>"
}

Important instructions:
- Return only numeric values (no dollar signs, commas, or other formatting)
- If you cannot find a value, return null for that field
- Set confidence_level to:
  * "high" if you found clear, unambiguous values
  * "medium" if you found likely values but with some uncertainty
  * "low" if you could not find clear values or if the document quality is poor
- Include any relevant notes about what you found or issues encountered
- Be precise and conservative in your extraction

The document you're analyzing is a Form 990 nonprofit tax filing. Focus specifically on finding these two key financial metrics.
"""

    def parse_pdf_with_gemini(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Parse PDF using Gemini AI to extract financial data.
        
        Args:
            pdf_bytes: PDF content as bytes
            
        Returns:
            Dictionary with parsed financial data and metadata
        """
        try:
            logger.info("Starting Gemini PDF parsing")
            
            # Try File API first (more reliable)
            try:
                return self._parse_with_file_api(pdf_bytes)
            except Exception as e:
                logger.warning(f"File API parsing failed: {e}, trying direct parsing")
                return self._parse_with_direct_content(pdf_bytes)
                
        except Exception as e:
            logger.error(f"Error during Gemini PDF parsing: {e}")
            return self._create_error_response(f"Gemini API error: {e}")
    
    def _parse_with_file_api(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Parse PDF using Gemini's File API (upload first, then analyze)"""
        logger.info("Using Gemini File API for PDF parsing")
        
        # Upload the PDF file to Gemini
        import tempfile
        import os
        
        # Create a temporary file for upload
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(pdf_bytes)
            temp_file.flush()
            
            # Upload using file path
            uploaded_file = genai.upload_file(
                path=temp_file.name,
                mime_type="application/pdf"
            )
            
        # Clean up the temporary file
        try:
            os.unlink(temp_file.name)
        except Exception as e:
            logger.debug(f"Could not delete temp file: {e}")
        
        logger.info(f"PDF uploaded to Gemini, file URI: {uploaded_file.uri}")
        
        # Create prompt
        prompt = self._create_prompt()
        
        # Generate response using the uploaded file
        response = self.model.generate_content([prompt, uploaded_file])
        
        # Clean up the uploaded file
        try:
            genai.delete_file(uploaded_file.name)
            logger.debug("Cleaned up uploaded file from Gemini")
        except Exception as e:
            logger.warning(f"Could not delete uploaded file: {e}")
        
        return self._process_gemini_response(response.text, "file_api")
    
    def _parse_with_direct_content(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Parse PDF using direct content (legacy method)"""
        logger.info("Using direct content parsing for PDF")
        
        # Convert PDF to base64 for Gemini
        pdf_base64 = self._convert_pdf_to_base64(pdf_bytes)
        
        # Create the file object for Gemini
        pdf_file = {
            'mime_type': 'application/pdf',
            'data': pdf_base64
        }
        
        # Create prompt
        prompt = self._create_prompt()
        
        # Generate response from Gemini
        response = self.model.generate_content([prompt, pdf_file])
        
        return self._process_gemini_response(response.text, "direct_content")
    
    def _process_gemini_response(self, response_text: str, method: str) -> Dict[str, Any]:
        """Process Gemini response text and extract financial data"""
        response_text = response_text.strip()
        logger.debug(f"Gemini response ({method}): {response_text}")
        
        try:
            import json
            # Look for JSON in the response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                response_data = json.loads(json_str)
                
                # Validate response using Pydantic
                financial_data = FinancialDataResponse(**response_data)
                
                result = {
                    "success": True,
                    "method": f"gemini_{method}",
                    "total_revenue": financial_data.total_revenue,
                    "total_executive_compensation": financial_data.total_executive_compensation,
                    "confidence_level": financial_data.confidence_level,
                    "notes": financial_data.notes,
                    "raw_response": response_text
                }
                
                logger.info(f"Gemini parsing completed with confidence: {financial_data.confidence_level}")
                return result
                
            else:
                logger.error("Could not find valid JSON in Gemini response")
                return self._create_error_response("Invalid JSON response from Gemini", response_text)
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON response: {e}")
            return self._create_error_response(f"JSON parsing error: {e}", response_text)
            
        except Exception as e:
            logger.error(f"Error validating Gemini response: {e}")
            return self._create_error_response(f"Response validation error: {e}", response_text)
    
    def _create_error_response(self, error_message: str, raw_response: str = None) -> Dict[str, Any]:
        """Create a standardized error response."""
        return {
            "success": False,
            "method": "gemini",
            "error": error_message,
            "total_revenue": None,
            "total_executive_compensation": None,
            "confidence_level": "low",
            "notes": f"Error: {error_message}",
            "raw_response": raw_response
        }
    
    def parse_with_retry(self, pdf_bytes: bytes, max_retries: int = 2) -> Dict[str, Any]:
        """
        Parse PDF with retry logic for handling temporary API issues.
        
        Args:
            pdf_bytes: PDF content as bytes
            max_retries: Maximum number of retry attempts
            
        Returns:
            Dictionary with parsed financial data and metadata
        """
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Retrying Gemini parsing (attempt {attempt + 1}/{max_retries + 1}) after {wait_time}s")
                    time.sleep(wait_time)
                
                result = self.parse_pdf_with_gemini(pdf_bytes)
                
                if result.get("success"):
                    return result
                elif attempt == max_retries:
                    # Last attempt failed, return the error
                    return result
                else:
                    # Failed but we have more retries
                    logger.warning(f"Gemini parsing attempt {attempt + 1} failed: {result.get('error', 'Unknown error')}")
                    continue
                    
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"All Gemini parsing attempts failed. Final error: {e}")
                    return self._create_error_response(f"All retry attempts failed: {e}")
                else:
                    logger.warning(f"Gemini parsing attempt {attempt + 1} failed with exception: {e}")
                    continue
        
        return self._create_error_response("Unexpected error in retry logic")

def test_gemini_parser():
    """Test function for the Gemini parser (requires API key to be set)."""
    import os
    
    # Check if API key is available
    api_key = os.getenv('GOOGLE_AI_API_KEY')
    if not api_key:
        print("GOOGLE_AI_API_KEY environment variable not set. Cannot test Gemini parser.")
        return
    
    try:
        parser = GeminiPDFParser(api_key)
        print("Gemini parser initialized successfully")
        
        # You would need to provide actual PDF bytes here for testing
        # test_pdf_bytes = open("test_form_990.pdf", "rb").read()
        # result = parser.parse_with_retry(test_pdf_bytes)
        # print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(f"Error testing Gemini parser: {e}")

if __name__ == "__main__":
    test_gemini_parser()