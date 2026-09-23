// 示例：一段典型的 "AI 一把梭" 生成 JS 代码（故意埋入典型问题）
const API_KEY = "YOUR_API_KEY";

function saveUser(user) {
  // AI 爱用 eval 拼对象
  eval("users.push(" + JSON.stringify(user) + ")");
}

function render(html) {
  document.write(html); // XSS 风险
}

function load() {
  try {
    risky();
  } catch (e) {
  } // 空 catch，错误被静默吞掉
}

var config = { url: "https://example.com/api" }; // var + 占位符 URL
