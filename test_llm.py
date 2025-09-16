#!/usr/bin/env python3
"""Test script for LLM summarization"""

import os
from dotenv import load_dotenv
from llm_summarizer import create_summarizer

# Load environment variables
load_dotenv()

def test_summarizer():
    # Create test article
    test_article = {
        'title': 'OpenAI Announces GPT-5 with Enhanced Reasoning Capabilities',
        'summary': 'OpenAI has unveiled GPT-5, featuring significant improvements in logical reasoning, mathematical problem-solving, and reduced hallucinations. The model demonstrates 40% better performance on complex reasoning benchmarks.',
        'link': 'https://example.com/gpt5-announcement',
        'feed_name': 'OpenAI Blog',
        'category': 'Research Labs'
    }
    
    # Get backend from environment
    backend = os.getenv('LLM_BACKEND', 'ollama')
    model = os.getenv('LLM_MODEL', 'llama3.2')
    base_url = os.getenv('LLM_BASE_URL', 'http://localhost:11434')
    
    print(f"\n{'='*50}")
    print(f"Testing {backend} backend...")
    print(f"Model: {model}")
    print(f"Base URL: {base_url}")
    print('='*50)
    
    try:
        if backend == 'transformer' or backend == 'flan-t5':
            print("\n🤖 Using built-in transformer model...")
            print("First run will download the model (may take a few minutes)")
            
        elif backend == 'ollama':
            # Check if Ollama is running
            import requests
            try:
                response = requests.get(f"{base_url}/api/tags", timeout=2)
                if response.status_code != 200:
                    print("\n❌ Ollama is not running!")
                    print("\nTo fix this:")
                    print("1. Install Ollama: https://ollama.ai")
                    print("2. Start Ollama: ollama serve")
                    print(f"3. Pull the model: ollama pull {model}")
                    return
                    
                # Check if model exists
                models = response.json().get('models', [])
                model_names = [m['name'] for m in models]
                
                if not any(model in name for name in model_names):
                    print(f"\n❌ Model '{model}' not found!")
                    print(f"\nTo fix this: ollama pull {model}")
                    if model_names:
                        print(f"\nAvailable models: {', '.join(model_names)}")
                    return
                    
            except requests.exceptions.ConnectionError:
                print("\n❌ Cannot connect to Ollama!")
                print("\nTo fix this:")
                print("1. Install Ollama: https://ollama.ai")
                print("2. Start Ollama: ollama serve")
                print(f"3. Pull the model: ollama pull {model}")
                return
        
        elif backend == 'llamacpp':
            # Check if llama.cpp server is running
            import requests
            try:
                response = requests.get(f"{base_url}/health", timeout=2)
                if response.status_code != 200:
                    print("\n❌ llama.cpp server is not running!")
                    print("\nTo fix this:")
                    print("1. Start your llama.cpp server")
                    print(f"2. Make sure it's running on {base_url}")
                    return
            except:
                print("\n❌ Cannot connect to llama.cpp server!")
                print(f"\nMake sure llama.cpp server is running on {base_url}")
                return
        
        # Create summarizer and test
        if backend in ['transformer', 'flan-t5']:
            summarizer = create_summarizer(
                backend=backend,
                model_name=model
            )
        else:
            summarizer = create_summarizer(
                backend=backend,
                base_url=base_url,
                model=model if backend == 'ollama' else None
            )
        
        print("\n📝 Generating summary for test article...")
        summary = summarizer.summarize(test_article)
        
        if summary:
            print("\n✅ Success! Generated summary:")
            print("-" * 50)
            print(summary)
            print("-" * 50)
            print("\n🎉 LLM integration is working! The bot will now generate AI summaries for articles.")
        else:
            print("\n❌ Failed to generate summary")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_summarizer()