# FontByte

FontByte is a tool designed to help developers and designers make informed decisions about variable fonts based on both aesthetic and technical criteria. While the visual appeal of a font is crucial, FontByte emphasizes the importance of considering performance and functionality in font selection.

## Purpose

The main goals of FontByte are to:

1. **Performance Analysis**: Evaluate variable fonts based on their file sizes to help optimize web performance and loading times.

2. **Feature Exploration**: Analyze and display supported variable axes (like weight, width, slant, etc.) to help users understand the full range of typographic possibilities each font offers.

3. **Informed Decision Making**: Combine aesthetic considerations with technical metrics to help users choose fonts that are not only visually appealing but also performant and feature-rich.

## Why FontByte?

Traditional font selection tools often focus solely on visual characteristics. However, in modern web development, factors like:
- File size impact on page load times
- Browser compatibility
- Available variable axes for responsive typography
- Performance implications of font loading

are equally important. FontByte bridges this gap by providing a comprehensive view of both the visual and technical aspects of variable fonts.

## Current Implementation

FontByte currently operates as follows:

1. **Data Collection**: The tool analyzes variable fonts distributed by Fontsource, creating a comprehensive dataframe containing file size information for each font.

2. **Data Publishing**: The dataframe is published on GitHub Pages as a static `ITable` component.

### Advantages of Current Approach
- **Easy Deployment**: Using GitHub Pages for hosting means the data is readily accessible without complex server setup
- **Zero Infrastructure**: No need for backend servers or databases
- **Fast Loading**: Static content delivery through GitHub's CDN
- **Reliable**: Leverages GitHub's robust infrastructure

### Using the Table

The `ITable` component provides basic but useful filtering and sorting capabilities:

- **Column Sorting**: Click on any column header to sort the data
- **Search/Filter**: Each column has a search field at the bottom
  - Example: Type `serif` in the Category column's search bar to display only serif fonts
  - Multiple filters can be combined across different columns
  - Filtering is case-insensitive and matches partial text

### Current Limitations
- **Limited Interactivity**: The static `ITable` implementation restricts more advanced dynamic features
- **Fixed Dataset**: Updates require regenerating and republishing the data
- **Basic Filtering**: While useful for simple queries, the search capabilities are constrained by `ITable`'s built-in features
  - No regular expressions support
  - No complex queries or combinations using OR/AND operators
  - Cannot save or share filtered views

Future versions may explore more dynamic solutions while maintaining the simplicity of deployment.

## Getting Started

[Coming Soon]

## Contributing

We welcome contributions! Whether you're interested in:
- Adding new font analysis features
- Improving performance metrics
- Enhancing the user interface
- Fixing bugs
- Writing documentation

### Development Environment

This project includes a devcontainer configuration, making it easy to get started with development:

- **Consistent Environment**: The devcontainer ensures all developers work with the same development environment
- **Pre-configured Tools**: All necessary dependencies and tools are automatically installed
- **VS Code Integration**: Works seamlessly with VS Code's Remote - Containers extension
- **Ready to Code**: Just open the project in VS Code with the Remote - Containers extension, and you're ready to start coding

To use the devcontainer:
1. Install Docker and VS Code with the Remote - Containers extension
2. Clone the repository
3. Open in VS Code - it will automatically detect and offer to reopen in container
4. All dependencies will be installed automatically

Please check our contributing guidelines for more information about the development workflow and code standards.
