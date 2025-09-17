import logging
import requests
import json
from typing import Optional, Dict
from abc import ABC, abstractmethod
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline
import os

logger = logging.getLogger(__name__)


class LLMSummarizer(ABC):
    """Abstract base class for LLM summarizers"""
    
    @abstractmethod
    def summarize(self, article: Dict) -> Optional[str]:
        """Generate a summary for an article"""
        pass


class OllamaSummarizer(LLMSummarizer):
    """Summarizer using Ollama local LLM"""
    
    def __init__(self, base_url: str = "http://localhost:11434", 
                 model: str = "llama3.2", 
                 max_tokens: int = 150):
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        
    def summarize(self, article: Dict) -> Optional[str]:
        """Generate summary using Ollama"""
        try:
            # Prepare the prompt
            prompt = self._create_prompt(article)
            
            # Call Ollama API
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": self.max_tokens,
                        "temperature": 0.3,
                        "top_p": 0.9
                    }
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                summary = result.get("response", "").strip()
                logger.info(f"Generated summary for: {article['title'][:50]}...")
                return summary
            else:
                logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                
        except requests.exceptions.ConnectionError:
            logger.error("Could not connect to Ollama. Make sure it's running with: ollama serve")
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            
        return None
    
    def _create_prompt(self, article: Dict) -> str:
        """Create prompt for summarization"""
        content = f"Title: {article['title']}\n"
        if article.get('summary'):
            content += f"Description: {article['summary']}\n"
            
        prompt = f"""Please provide a brief 2-3 sentence summary of this AI news article. Focus on the key findings, announcements, or developments. Be concise and informative.

{content}

Summary:"""
        return prompt


class LlamaCppSummarizer(LLMSummarizer):
    """Summarizer using llama.cpp server"""
    
    def __init__(self, base_url: str = "http://localhost:8080", 
                 max_tokens: int = 150):
        self.base_url = base_url
        self.max_tokens = max_tokens
        
    def summarize(self, article: Dict) -> Optional[str]:
        """Generate summary using llama.cpp server"""
        try:
            prompt = self._create_prompt(article)
            
            response = requests.post(
                f"{self.base_url}/completion",
                json={
                    "prompt": prompt,
                    "n_predict": self.max_tokens,
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "stop": ["\n\n", "Title:", "Description:"]
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                summary = result.get("content", "").strip()
                logger.info(f"Generated summary for: {article['title'][:50]}...")
                return summary
            else:
                logger.error(f"llama.cpp API error: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            logger.error("Could not connect to llama.cpp server")
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            
        return None
    
    def _create_prompt(self, article: Dict) -> str:
        """Create prompt for summarization"""
        content = f"Title: {article['title']}\n"
        if article.get('summary'):
            content += f"Description: {article['summary']}\n"
            
        prompt = f"""Please provide a brief 2-3 sentence summary of this AI news article. Focus on the key findings, announcements, or developments. Be concise and informative.

{content}

Summary:"""
        return prompt


class TransformerSummarizer(LLMSummarizer):
    """Built-in summarizer using Hugging Face transformers"""
    
    def __init__(self, model_name: str = "facebook/bart-large-cnn", 
                 max_length: int = 150, 
                 min_length: int = 50,
                 device: str = None):
        self.model_name = model_name
        self.max_length = max_length
        self.min_length = min_length
        
        # Determine device
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        logger.info(f"Initializing transformer model '{model_name}' on {self.device}")
        
        # Create cache directory
        self.cache_dir = os.path.expanduser("~/.cache/slackwire/models")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        try:
            # Initialize the summarization pipeline
            self.summarizer = pipeline(
                "summarization",
                model=model_name,
                device=0 if self.device == "cuda" else -1,
                cache_dir=self.cache_dir
            )
            logger.info(f"Model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def summarize(self, article: Dict) -> Optional[str]:
        """Generate summary using transformer model"""
        try:
            # Prepare the text
            text = self._prepare_text(article)
            
            # Generate summary
            result = self.summarizer(
                text,
                max_length=self.max_length,
                min_length=self.min_length,
                do_sample=False,
                truncation=True
            )
            
            if result and len(result) > 0:
                summary = result[0]['summary_text']
                # Clean up the summary
                summary = summary.strip()
                # Add context about what the article is about
                summary = f"{summary} The article is from {article.get('feed_name', 'an AI news source')}."
                logger.info(f"Generated summary for: {article['title'][:50]}...")
                return summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            
        return None
    
    def _prepare_text(self, article: Dict) -> str:
        """Prepare article text for summarization"""
        # Combine title and description/summary
        parts = []
        
        # Add title
        if article.get('title'):
            parts.append(f"Title: {article['title']}")
            
        # Add existing summary/description
        if article.get('summary'):
            parts.append(f"Article: {article['summary']}")
            
        # Join with newlines
        text = "\n".join(parts)
        
        # Ensure text isn't too long (BART has a 1024 token limit)
        if len(text) > 1024:
            text = text[:1024]
            
        return text


class FlantT5Summarizer(LLMSummarizer):
    """Summarizer using Google's Flan-T5 model"""
    
    def __init__(self, model_name: str = "google/flan-t5-base", 
                 max_length: int = 150,
                 device: str = None):
        self.model_name = model_name
        self.max_length = max_length
        
        # Determine device
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        logger.info(f"Initializing Flan-T5 model '{model_name}' on {self.device}")
        
        # Create cache directory
        self.cache_dir = os.path.expanduser("~/.cache/slackwire/models")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        try:
            # Load tokenizer and model
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_name, 
                cache_dir=self.cache_dir
            )
            self.model = AutoModelForSeq2SeqLM.from_pretrained(
                model_name,
                cache_dir=self.cache_dir
            )
            self.model.to(self.device)
            self.model.eval()
            logger.info(f"Flan-T5 model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load Flan-T5 model: {e}")
            raise
    
    def summarize(self, article: Dict) -> Optional[str]:
        """Generate summary using Flan-T5"""
        try:
            # Create prompt
            prompt = self._create_prompt(article)
            
            # Tokenize input
            inputs = self.tokenizer(
                prompt, 
                return_tensors="pt", 
                max_length=512, 
                truncation=True
            ).to(self.device)
            
            # Generate summary
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_length=self.max_length,
                    min_length=30,
                    temperature=0.7,
                    do_sample=False,
                    num_beams=4,
                    early_stopping=True
                )
            
            # Decode the output
            summary = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            if summary:
                # Check for repetitive patterns (common with insufficient context)
                words = summary.split()
                if len(words) > 10:
                    # Check if the same phrase is repeated more than 3 times
                    for i in range(len(words) - 3):
                        phrase = ' '.join(words[i:i+3])
                        if summary.count(phrase) > 3:
                            logger.warning(f"Detected repetitive summary for: {article['title'][:50]}...")
                            # Fallback to a simple extraction
                            title = article.get('title', '')
                            content = article.get('summary', '')
                            feed_name = article.get('feed_name', '')
                            if 'ArXiv' in feed_name:
                                first_sentence = content.split('.')[0] if content else ''
                                return f"New research paper on {title.lower()}. {first_sentence}."
                            else:
                                first_sentence = content.split('.')[0] if content else ''
                                return f"Article about {title.lower()}. {first_sentence}."
                
                logger.info(f"Generated summary for: {article['title'][:50]}...")
                return summary.strip()
                
        except Exception as e:
            logger.error(f"Error generating summary with Flan-T5: {e}")
            
        return None
    
    def _create_prompt(self, article: Dict) -> str:
        """Create prompt for Flan-T5 summarization"""
        title = article.get('title', '')
        content = article.get('summary', '')
        feed_name = article.get('feed_name', '')
        
        # Special handling for ArXiv papers
        if 'ArXiv' in feed_name and content:
            # ArXiv summaries are abstracts, so we need a different prompt
            prompt = f"""Based on this research paper abstract, provide a 2-3 sentence summary highlighting the key contributions and findings:

Title: {title}
Abstract: {content}

Summary:"""
        else:
            prompt = f"""Summarize this AI news article in 2-3 sentences:

Title: {title}
Content: {content}

Summary:"""
        return prompt


def create_summarizer(backend: str = "transformer", **kwargs) -> LLMSummarizer:
    """Factory function to create appropriate summarizer"""
    if backend == "transformer":
        return TransformerSummarizer(**kwargs)
    elif backend == "flan-t5":
        return FlantT5Summarizer(**kwargs)
    elif backend == "ollama":
        return OllamaSummarizer(**kwargs)
    elif backend == "llamacpp":
        return LlamaCppSummarizer(**kwargs)
    else:
        raise ValueError(f"Unknown LLM backend: {backend}")