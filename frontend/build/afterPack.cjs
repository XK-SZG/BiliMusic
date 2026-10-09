const fs = require('fs');
const path = require('path');

exports.default = async function(context) {
  if (context.electronPlatformName !== 'win32') return;

  const appOutDir = context.appOutDir;
  const nshPath = path.join(context.packager.projectDir, 'build', 'uninstall_list.nsh');
  
  let script = `!macro customRemoveFiles\n`;
  script += `  \${If} $R9 == "0"\n`;
  script += `    RMDir /r "$INSTDIR"\n`;
  script += `  \${Else}\n`;
  script += `    CreateDirectory "$PLUGINSDIR\\old-install"\n`;

  const files = [];
  const dirs = new Set();

  function traverse(currentPath, relativePath = '') {
    const items = fs.readdirSync(currentPath);
    for (const item of items) {
      const fullPath = path.join(currentPath, item);
      const itemRelativePath = relativePath ? `${relativePath}\\${item}` : item;
      const stat = fs.statSync(fullPath);
      
      if (stat.isDirectory()) {
        dirs.add(itemRelativePath);
        traverse(fullPath, itemRelativePath);
      } else {
        files.push(itemRelativePath);
      }
    }
  }

  traverse(appOutDir);

  // Create directories in old-install
  const sortedDirs = Array.from(dirs).sort();
  for (const dir of sortedDirs) {
    script += `    CreateDirectory "$PLUGINSDIR\\old-install\\${dir}"\n`;
  }

  // Rename files to old-install
  for (const file of files) {
    script += `    Rename "$INSTDIR\\${file}" "$PLUGINSDIR\\old-install\\${file}"\n`;
  }

  // Remove directories in INSTDIR (will only succeed if empty)
  // Sort descending by depth to remove subdirectories first
  const reverseDirs = Array.from(dirs).sort((a, b) => b.split('\\').length - a.split('\\').length);
  for (const dir of reverseDirs) {
    script += `    RMDir "$INSTDIR\\${dir}"\n`;
  }

  script += `  \${EndIf}\n`;
  script += `!macroend\n\n`;

  script += `!macro cleanOldFiles\n`;
  script += `  CreateDirectory "$PLUGINSDIR\\old-install"\n`;
  for (const dir of sortedDirs) {
    script += `  CreateDirectory "$PLUGINSDIR\\old-install\\${dir}"\n`;
  }
  for (const file of files) {
    script += `  Rename "$INSTDIR\\${file}" "$PLUGINSDIR\\old-install\\${file}"\n`;
  }
  for (const dir of reverseDirs) {
    script += `  RMDir "$INSTDIR\\${dir}"\n`;
  }
  script += `!macroend\n`;
  
  fs.writeFileSync(nshPath, script);
};
