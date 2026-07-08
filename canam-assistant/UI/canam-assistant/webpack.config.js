    const path = require("path");
    module.exports = {
      mode: "production",
      entry: {
        "bundle.js": [
          path.resolve(__dirname, "dist/canam-assistant/browser/polyfills.js"),
          path.resolve(__dirname, "dist/canam-assistant/browser/styles.css"),
          path.resolve(__dirname, "dist/canam-assistant/browser/main.js"),
        ],
      },
      output: {
        filename: "[name]",
        path: path.resolve(__dirname, "dist"),
      },
      module: {
        rules: [
          {
            test: /\.css$/i,
            use: ["style-loader", "css-loader"],
          },
        ],
      },
    };