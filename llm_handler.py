"""
LLM Handler Module - Integrates with Groq API for LLaMA
Generates simplified legal awareness responses with context
"""

from typing import Optional
import logging

try:
    from groq import Groq
except ImportError:
    Groq = None
    logging.warning("Groq client not installed. Install with: pip install groq")

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GroqLLMHandler:
    """
    Handles communication with Groq API for LLaMA LLM.
    Generates legal awareness responses based on retrieved context.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Groq LLM handler.
        
        Args:
            api_key (str): Groq API key (defaults to config)
        """
        self.api_key = api_key or config.GROQ_API_KEY
        self.model = config.LLM_MODEL
        self.temperature = config.LLM_TEMPERATURE
        self.max_tokens = config.LLM_MAX_TOKENS
        
        if Groq is None:
            logger.error("Groq client not installed")
            raise ImportError("Groq client not available")
        
        try:
            logger.info(f"Initializing Groq client with model: {self.model}")
            self.client = Groq(api_key=self.api_key)
            logger.info("Groq LLM handler initialized")
        except Exception as e:
            logger.error(f"Error initializing Groq: {str(e)}")
            raise
    
    def generate_response(self, query: str, context: str, language: str = "en") -> str:
        """
        Generate a legal awareness response using LLaMA.
        
        Args:
            query (str): User question
            context (str): Retrieved legal context from RAG
            language (str): "en" or "ta"
            
        Returns:
            str: Generated response
        """
        language = (language or "en").lower()
        language_name = "Tamil (தமிழ்)" if language == "ta" else "English"
        if language == "ta":
            format_instructions = (
                "Output format (use only Tamil words and Tamil script; do NOT use any English words):\n"
                "1. பிரிவு மற்றும் தலைப்பு: <பிரிவு எண் + தலைப்பு>\n"
                "2. சட்ட வரையறை: <சூழலிலிருந்து நேரடியாக பெறப்பட்ட வாக்கியம்/வாக்கியங்கள்>\n"
                "3. எளிய விளக்கம்: <சூழலில் உள்ள தகவலை எளிதாக சொல்>\n"
                "4. தண்டனை: <சூழலில் இருந்தால் மட்டும்>\n"
                "5. உதாரணம்: <சூழலில் இருந்தால் மட்டும்>\n"
                "If any field is not stated in the provided context, write: \"சூழலில் குறிப்பிடப்படவில்லை\"."
            )
        else:
            format_instructions = (
                "Output format:\n"
                "1. Section and Title: <section number + title>\n"
                "2. Legal Definition: <sentence(s) taken directly from the context>\n"
                "3. Simple Explanation: <explain using only context content>\n"
                "4. Punishment: <only if stated in the context>\n"
                "5. Example: <only if stated in the context>\n"
                "If any field is not stated in the provided context, write: \"Not stated in the provided context.\""
            )

        # Prepare prompt with instructions
        system_prompt = f"""You are an NLP-based Legal Aid Chatbot.

MANDATORY RULES:
1. Answer strictly based on the provided context. Do not use external knowledge.
2. If the context is insufficient to answer, explicitly say so.
3. Do NOT guess or hallucinate IPC sections.
4. Use ONLY the context wording; do not add facts that are not in the context.
5. Use a structured, grounded format exactly as specified below.
6. Use simple, clear, citizen-friendly language.
7. Do NOT give case-specific advice.
8. Do NOT suggest actions like filing cases or approaching police.
9. Respond ONLY in {language_name}.
10. Do not mix languages. If responding in Tamil, use only Tamil script (no Latin letters).

{format_instructions}
# -*- coding: utf-8 -*-
"""
        
        user_prompt = f"""Based on the following legal context, please answer the user's question.
Respond ONLY in {language_name}.

LEGAL CONTEXT:
{context}

USER QUESTION:
{query}

Please provide a clear, simplified explanation suitable for someone without legal background."""
        
        try:
            logger.info("Calling Groq API for response generation...")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=0.95,
                stream=False
            )
            
            generated_text = response.choices[0].message.content.strip()
            logger.info("Response generated successfully")
            
            return generated_text
        
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return f"I apologize, but I encountered an error while processing your question. Error: {str(e)}"
    
    def generate_rag_response(self, query: str, context: str, language: str = "en") -> str:
        """
        Generate RAG response (main method for chatbot).
        
        Args:
            query (str): User question
            context (str): Retrieved legal documents context
            language (str): "en" or "ta"
            
        Returns:
            str: Final response with disclaimer
        """
        # Generate response
        response = self.generate_response(query, context, language=language)
        return response

    def translate_text(self, text: str, target_language: str) -> str:
        """
        Translate text into the target language using the existing Groq model.
        Supported: "ta" (Tamil) only.
        """
        if target_language != "ta":
            return text
        language_name = "Tamil (தமிழ்)"
        system_prompt = (
            "You are a precise translation assistant for legal information. "
            "Translate the given text faithfully without adding or removing meaning. "
            "Preserve numbering, formatting, and legal disclaimer. "
            "Do not add explanations or extra commentary. "
            "Use only Tamil script and do not include any Latin letters or English words."
        )
        user_prompt = (
            f"Translate the following text into {language_name}. "
            "Use only Tamil script (Unicode) and do not include any Latin letters.\n\n"
            f"TEXT:\n{text}"
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=min(self.max_tokens, 700),
            top_p=0.95,
            stream=False,
        )
        return response.choices[0].message.content.strip()


class ResponseFormatter:
    """
    Formats LLM responses for better readability in Streamlit UI.
    """
    
    @staticmethod
    def format_response(response: str) -> str:
        """
        Format response with better structure.
        
        Args:
            response (str): Raw response text
            
        Returns:
            str: Formatted response
        """
        # Remove extra whitespace
        response = " ".join(response.split())
        return response
    
    @staticmethod
    def add_sources(response: str, sources: list) -> str:
        """
        Append source attribution to response.
        
        Args:
            response (str): Response text
            sources (list): List of source documents
            
        Returns:
            str: Response with sources
        """
        sources_text = "\n\n**Sources Referenced:**\n"
        for i, source in enumerate(sources, 1):
            sources_text += f"{i}. {source}\n"
        
        return response + sources_text
    
    @staticmethod
    def highlight_key_terms(response: str) -> str:
        """
        Highlight important legal terms in response.
        
        Args:
            response (str): Response text
            
        Returns:
            str: Response with highlighted terms
        """
        important_terms = [
            "right", "law", "legal", "court", "judge", "contract",
            "agreement", "penalty", "compensation", "liability"
        ]
        
        formatted_response = response
        for term in important_terms:
            # Case-insensitive replacement
            formatted_response = formatted_response.replace(
                term,
                f"**{term}**"
            )
        
        return formatted_response


class ResponseValidator:
    """
    Validates that responses are legal-appropriate and contain disclaimer.
    """
    
    @staticmethod
    def validate_response(response: str) -> bool:
        """
        Check if response is valid and contains required disclaimer.
        
        Args:
            response (str): Response to validate
            
        Returns:
            bool: True if response is valid
        """
        # Check if response contains disclaimer
        has_disclaimer = "LEGAL DISCLAIMER" in response or "does not constitute legal advice" in response
        
        # Check minimum length
        has_content = len(response) > 50
        
        return has_disclaimer and has_content
    
    @staticmethod
    def ensure_disclaimer(response: str, language: str = "en") -> str:
        """
        Ensure response includes legal disclaimer.
        
        Args:
            response (str): Response text
            language (str): "en" or "ta"
            
        Returns:
            str: Response with disclaimer
        """
        language = (language or "en").lower()
        if language == "ta":
            disclaimer_text = config.LEGAL_DISCLAIMER_TA
            label = "சட்ட அறிவிப்பு"
        else:
            disclaimer_text = config.LEGAL_DISCLAIMER
            label = "Legal Disclaimer"
        disclaimer = f"**{label}:** {disclaimer_text}"
        if disclaimer_text not in response:
            response = f"{response}\n\n{disclaimer}"
        
        return response


# ==================== TESTING FUNCTION ====================
if __name__ == "__main__":
    logger.info("LLM Handler module ready for use")
    
    # Example usage (requires valid Groq API key)
    """
    handler = GroqLLMHandler()
    
    sample_context = \"\"\"
    Right to Education Act: Every child has the right to free and compulsory education 
    up to the age of 14 years as per Article 21-A of the Constitution.
    \"\"\"
    
    sample_query = "What is the right to education in India?"
    
    response = handler.generate_rag_response(sample_query, sample_context)
    print(response)
    """
