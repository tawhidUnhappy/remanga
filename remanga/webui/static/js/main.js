// Entry point: pulls in every module for its side effects (each one wires up
// its own DOM listeners on import) and then boots the app. Loaded from
// index.html as <script type="module" src="/static/js/main.js">.

import "./draw.js";
import "./drag-resize.js";
import "./zoom-pan.js";
import "./keyboard.js";
import "./magi.js";
import { init } from "./page-nav.js";

init();
