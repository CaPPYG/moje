package online.garcarzp.braindump.widget

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

data class TaskWidgetItem(
    val id: Int,
    val text: String,
    val category: String
)

class WidgetPreferences(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString(KEY_SERVER_URL, DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL
        set(value) = prefs.edit().putString(KEY_SERVER_URL, value).apply()

    var apiUrl: String
        get() = prefs.getString(KEY_API_URL, DEFAULT_API_URL) ?: DEFAULT_API_URL
        set(value) = prefs.edit().putString(KEY_API_URL, value).apply()

    var masterPassword: String
        get() = prefs.getString(KEY_MASTER_PASSWORD, DEFAULT_PASSWORD) ?: DEFAULT_PASSWORD
        set(value) = prefs.edit().putString(KEY_MASTER_PASSWORD, value).apply()

    var totalOpen: Int
        get() = prefs.getInt(KEY_TOTAL_OPEN, 0)
        set(value) = prefs.edit().putInt(KEY_TOTAL_OPEN, value).apply()

    fun saveTasks(totalOpen: Int, tasks: List<TaskWidgetItem>) {
        val jsonArray = JSONArray()
        for (t in tasks) {
            val obj = JSONObject().apply {
                put("id", t.id)
                put("text", t.text)
                put("category", t.category)
            }
            jsonArray.put(obj)
        }
        prefs.edit()
            .putInt(KEY_TOTAL_OPEN, totalOpen)
            .putString(KEY_TASKS_JSON, jsonArray.toString())
            .apply()
    }

    fun getCachedTasks(): List<TaskWidgetItem> {
        val raw = prefs.getString(KEY_TASKS_JSON, null) ?: return emptyList()
        val list = mutableListOf<TaskWidgetItem>()
        try {
            val jsonArray = JSONArray(raw)
            for (i in 0 until jsonArray.length()) {
                val obj = jsonArray.getJSONObject(i)
                list.add(
                    TaskWidgetItem(
                        id = obj.optInt("id", 0),
                        text = obj.optString("text", ""),
                        category = obj.optString("category", "Other")
                    )
                )
            }
        } catch (_: Exception) {
            // fallback empty
        }
        return list
    }

    companion object {
        private const val PREFS_NAME = "braindump_widget_prefs"
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_API_URL = "api_url"
        private const val KEY_MASTER_PASSWORD = "master_password"
        private const val KEY_TOTAL_OPEN = "total_open"
        private const val KEY_TASKS_JSON = "tasks_json"

        const val DEFAULT_SERVER_URL = "https://garcarzp.online/braindump/"
        const val DEFAULT_API_URL = "https://garcarzp.online/braindump/api/tasks/widget"
        const val DEFAULT_PASSWORD = "patrik3924"
    }
}
