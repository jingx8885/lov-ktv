package com.lovktv.phone

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.Button
import android.widget.TextView

class RowAdapter(
    private val inflater: LayoutInflater,
    private val onAction: (Row) -> Unit,
) : BaseAdapter() {
    data class Row(
        val key: String,
        val title: String,
        val meta: String,
        val action: String,
        val enabled: Boolean = true,
        val payload: Any? = null,
    )

    private val items = mutableListOf<Row>()

    fun replace(rows: List<Row>) {
        items.clear()
        items.addAll(rows)
        notifyDataSetChanged()
    }

    override fun getCount(): Int = items.size

    override fun getItem(position: Int): Row = items[position]

    override fun getItemId(position: Int): Long = items[position].key.hashCode().toLong()

    override fun getView(position: Int, convertView: View?, parent: ViewGroup?): View {
        val view = convertView ?: inflater.inflate(R.layout.item_row, parent, false)
        val row = items[position]
        view.findViewById<TextView>(R.id.title).text = row.title
        view.findViewById<TextView>(R.id.meta).text = row.meta
        val button = view.findViewById<Button>(R.id.action)
        button.text = row.action
        button.isEnabled = row.enabled
        button.setOnClickListener { onAction(row) }
        return view
    }
}
