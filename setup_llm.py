#!/usr/bin/env python3
"""Setup script for LLM components"""

import os
import sys
import subprocess
from pathlib import Path

def check_dependencies():
    """Check if required packages are installed"""
    try:
        import torch
        import transformers
        print("✅ PyTorch and Transformers are installed")
        return True
    except ImportError:
        print("❌ Missing dependencies")
        return False

def install_dependencies():
    """Install required packages"""
    print("\n📦 Installing LLM dependencies...")
    print("This may take a few minutes...")
    
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", 
                             "torch", "transformers", "accelerate"])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def download_model():
    """Pre-download the model"""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    backend = os.getenv('LLM_BACKEND', 'flan-t5')
    model_name = os.getenv('LLM_MODEL', 'google/flan-t5-small')
    
    print(f"\n🤖 Downloading AI model: {model_name}")
    
    if backend == 'transformer' and 'bart' in model_name:
        print("This will download the BART-CNN model (~1.6GB)")
    elif 'flan-t5-small' in model_name:
        print("This will download the Flan-T5 Small model (~250MB)")
    elif 'flan-t5-base' in model_name:
        print("This will download the Flan-T5 Base model (~990MB)")
    
    print("The model will be cached for future use")
    
    try:
        # Create cache directory
        cache_dir = os.path.expanduser("~/.cache/slackwire/models")
        os.makedirs(cache_dir, exist_ok=True)
        
        if backend == 'transformer':
            from transformers import pipeline
            print("Downloading... (this may take several minutes)")
            summarizer = pipeline(
                "summarization",
                model=model_name,
                cache_dir=cache_dir
            )
            # Test it
            test_text = "This is a test article about artificial intelligence."
            result = summarizer(test_text, max_length=50, min_length=10)
        else:
            # Flan-T5
            from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
            print("Downloading tokenizer...")
            tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir)
            print("Downloading model...")
            model = AutoModelForSeq2SeqLM.from_pretrained(model_name, cache_dir=cache_dir)
            
            # Test it
            test_input = tokenizer("Summarize: This is a test.", return_tensors="pt")
            outputs = model.generate(**test_input, max_length=50)
            result = tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        print("✅ Model downloaded and tested successfully!")
        print(f"Model cached at: {cache_dir}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to download model: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 SlackWire LLM Setup")
    print("=" * 50)
    
    # Check if already set up
    if check_dependencies():
        print("\n🎉 LLM components are already set up!")
        
        # Ask if they want to download the model
        response = input("\nDownload the AI model now? (y/n): ").lower()
        if response == 'y':
            download_model()
    else:
        # Install dependencies
        response = input("\nInstall LLM dependencies? (y/n): ").lower()
        if response != 'y':
            print("Setup cancelled")
            return
            
        if not install_dependencies():
            print("Setup failed")
            return
            
        # Download model
        response = input("\nDownload the AI model now? (y/n): ").lower()
        if response == 'y':
            download_model()
    
    print("\n✅ Setup complete!")
    print("\nTo test the LLM integration, run:")
    print("  python test_llm.py")

if __name__ == "__main__":
    main()