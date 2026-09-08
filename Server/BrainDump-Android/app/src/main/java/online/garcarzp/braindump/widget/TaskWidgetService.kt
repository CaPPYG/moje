package online.garcarzp.braindump.widget

import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import android.widget.RemoteViewsService
import online.garcarzp.braindump.R

class TaskWidgetService : RemoteViewsService() {
    override fun onGetViewFactory(intent: Intent): RemoteViewsFactory {
        return TaskRemoteViewsFactory(applicationContext)
    }
}

class TaskRemoteViewsFactory(private val context: Context) : RemoteViewsService.RemoteViewsFactory {

    private var taskList: List<TaskWidgetItem> = emptyList()
    private val prefs = WidgetPreferences(context)

    override fun onCreate() {
        taskList = prefs.getCachedTasks()
    }

    override fun onDataSetChanged() {
        taskList = prefs.getCachedTasks()
    }

    override fun onDestroy() {
        taskList = emptyList()
    }

    override fun getCount(): Int = taskList.size

    override fun getViewAt(position: Int): RemoteViews {
        if (position !in taskList.indices) {
            return RemoteViews(context.packageName, R.layout.widget_task_item)
        }

        val task = taskList[position]
        val views = RemoteViews(context.packageName, R.layout.widget_task_item)

        // Set task text
        views.setTextViewText(R.id.widget_item_text, task.text)

        // Set category label & corresponding dot color
        val (catLabel, catDotRes) = when (task.category) {
            "Work" -> "Work" to R.drawable.ic_cat_dot_work
            "Groceries" -> "Nákup" to R.drawable.ic_cat_dot_groceries
            "Personal" -> "Osobné" to R.drawable.ic_cat_dot_personal
            else -> "Iné" to R.drawable.ic_cat_dot_other
        }

        views.setTextViewText(R.id.widget_item_cat_name, catLabel)
        views.setImageViewResource(R.id.widget_item_cat_dot, catDotRes)

        // Fill-in Intent for item click (opens MainActivity)
        val fillInIntent = Intent().apply {
            putExtra("task_id", task.id)
            putExtra("task_text", task.text)
        }
        views.setOnClickFillInIntent(R.id.widget_item_root, fillInIntent)

        return views
    }

    override fun getLoadingView(): RemoteViews? = null

    override fun getViewTypeCount(): Int = 1

    override fun getItemId(position: Int): Long =
        if (position in taskList.indices) taskList[position].id.toLong() else position.toLong()

    override fun hasStableIds(): Boolean = true
}
