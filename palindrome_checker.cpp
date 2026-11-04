#include <iostream>
#include <string>
#include <algorithm>
#include <cctype>

// Function to clean the string by removing non-alphanumeric characters and converting to lowercase
std::string cleanString(const std::string& str) {
    std::string cleaned = "";
    for (char ch : str) {
        if (std::isalnum(static_cast<unsigned char>(ch))) {
            cleaned += std::tolower(static_cast<unsigned char>(ch));
        }
    }
    return cleaned;
}

// Function to check if a string is a palindrome
bool isPalindrome(const std::string& str) {
    std::string cleaned = cleanString(str);
    std::string reversed = cleaned;
    std::reverse(reversed.begin(), reversed.end());
    return cleaned == reversed;
}

int main() {
    std::cout << "========================================\n";
    std::cout << "       C++ PALINDROME CHECKER APP       \n";
    std::cout << "========================================\n";

    std::string input;
    char choice;

    do {
        std::cout << "\nEnter a word, phrase, or number to check: ";
        std::getline(std::cin >> std::ws, input);

        if (isPalindrome(input)) {
            std::cout << "[RESULT] YES! \"" << input << "\" is a palindrome.\n";
        } else {
            std::cout << "[RESULT] NO, \"" << input << "\" is NOT a palindrome.\n";
        }

        std::cout << "\nWould you like to check another? (y/n): ";
        std::cin >> choice;

    } while (choice == 'y' || choice == 'Y');

    std::cout << "\nThank you for using C++ Palindrome Checker! Exiting...\n";
    return 0;
}
