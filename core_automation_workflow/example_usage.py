#!/usr/bin/env python3
"""
Example usage of the Core Automation Workflow

This script demonstrates how to use the core automation workflow
to process case law documents through the LexisNexis system.
"""

import logging
from main_workflow import (
    run_automation_with_excel,
    run_automation_with_existing_excel,
    run_automation_workflow
)


def example_1_create_new_excel():
    """Example 1: Create a new Excel file and run automation"""
    print("Example 1: Create new Excel file and run automation")
    print("=" * 50)
    
    try:
        # This will create a new Excel file, open it for you to fill in data,
        # then run the automation once you press Enter
        success = run_automation_with_excel(dar_mode=False)
        
        if success:
            print("✅ Automation completed successfully!")
        else:
            print("❌ Automation failed. Check the logs for details.")
            
    except Exception as e:
        print(f"❌ Error: {e}")


def example_2_use_existing_excel():
    """Example 2: Use an existing Excel file"""
    print("\nExample 2: Use existing Excel file")
    print("=" * 50)
    
    # Replace with the path to your Excel file
    excel_path = "path/to/your/excel/file.xlsx"
    
    try:
        success = run_automation_with_existing_excel(excel_path, dar_mode=False)
        
        if success:
            print("✅ Automation completed successfully!")
        else:
            print("❌ Automation failed. Check the logs for details.")
            
    except Exception as e:
        print(f"❌ Error: {e}")


def example_3_dar_mode():
    """Example 3: Run in DAR mode"""
    print("\nExample 3: Run in DAR mode")
    print("=" * 50)
    
    try:
        success = run_automation_with_excel(dar_mode=True)
        
        if success:
            print("✅ DAR mode automation completed successfully!")
        else:
            print("❌ DAR mode automation failed. Check the logs for details.")
            
    except Exception as e:
        print(f"❌ Error: {e}")


def example_4_custom_workflow():
    """Example 4: Custom workflow with direct function calls"""
    print("\nExample 4: Custom workflow")
    print("=" * 50)
    
    try:
        # Import required modules
        import pandas as pd
        from core_automation import setup_logging, create_folders, generate_excel
        
        # Setup logging
        setup_logging()
        
        # Create folders and Excel file
        base_folder = create_folders()
        excel_path = generate_excel(base_folder)
        
        print(f"📁 Created Excel file: {excel_path}")
        print("📝 Please fill in the Excel file with your data and save it.")
        print("⏳ Press Enter when ready to continue...")
        input()
        
        # Read the data
        df = pd.read_excel(excel_path, sheet_name="Mapping Data", engine="openpyxl")
        print(f"📊 Loaded {len(df)} rows from Excel file")
        
        # Run automation with custom callbacks
        def update_progress(batch, current, total):
            print(f"🔄 {batch.capitalize()} batch: {current}/{total} ({current/total*100:.1f}%)")
        
        def set_status(status):
            print(f"📋 Status: {status}")
        
        def show_success(user_name, counsel_success, main_success, counsel_already, main_already, counsel_timeout, main_timeout):
            print(f"🎉 Success! Processed by: {user_name}")
            print(f"   Counsel: {counsel_success} successful, {counsel_already} already processed")
            print(f"   Main: {main_success} successful, {main_already} already processed")
        
        def show_error(error_msg):
            print(f"❌ Error: {error_msg}")
        
        # Run the automation
        counsel_df, main_df = run_automation_workflow(
            update_progress=update_progress,
            set_status=set_status,
            show_success=show_success,
            show_error=show_error,
            latest_excel=excel_path,
            df=df,
            dar_mode=False
        )
        
        if counsel_df is not None and main_df is not None:
            print("✅ Custom workflow completed successfully!")
        else:
            print("❌ Custom workflow failed.")
            
    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    """Main function to run examples"""
    print("Core Automation Workflow - Example Usage")
    print("=" * 50)
    print("This script demonstrates different ways to use the core automation workflow.")
    print()
    
    while True:
        print("Choose an example to run:")
        print("1. Create new Excel file and run automation")
        print("2. Use existing Excel file")
        print("3. Run in DAR mode")
        print("4. Custom workflow with callbacks")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        if choice == "1":
            example_1_create_new_excel()
        elif choice == "2":
            example_2_use_existing_excel()
        elif choice == "3":
            example_3_dar_mode()
        elif choice == "4":
            example_4_custom_workflow()
        elif choice == "5":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please enter 1-5.")
        
        print("\n" + "=" * 50 + "\n")


if __name__ == "__main__":
    main()
